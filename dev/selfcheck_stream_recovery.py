"""离线自检：备用 CDN、取流探测与实际播放器请求一致。"""
import os
import sys
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from ddm import bili  # noqa: E402


class Response:
    status_code = 200

    def __init__(self, chunks=None):
        self.chunks = chunks if chunks is not None else [b"FLV\x01\x05\x00\x00\x00\x09"]
        self.closed = False

    def iter_content(self, _size):
        yield from self.chunks

    def close(self):
        self.closed = True


class JsonResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def main() -> None:
    # HTTP 200 不能证明有视频：实际故障房间返回 flags=4 的纯 AAC FLV。
    for chunks, expected in (([b"FLV\x01\x04\x00\x00\x00\x09"], False),
                              ([b"FL", b"V\x01\x05", b"\x00\x00\x00\x09"], True),
                              ([b"FLV\x01\x01\x00\x00\x00\x09"], True),
                              ([b"F"], False), ([b"FL"], False), ([b"FLV"], False),
                              ([], False), ([b"#EXTM3U\n"], True)):
        response = Response(chunks)
        with mock.patch.object(bili.requests, "get", return_value=response):
            actual = bili._fetchable("http://cdn/live.flv", bili.STREAM_APP)
        assert actual == expected, (chunks, "流探测必须拒绝仅音频或截断的 FLV", actual)
        assert response.closed, "探测成功或拒绝响应后都必须关闭连接"

    with mock.patch.object(bili.requests, "get", return_value=Response()) as get:
        assert bili._fetchable("http://cdn/live.flv", bili.STREAM_APP)
        assert "cookies" not in get.call_args.kwargs, \
            "探测请求不能用播放器没有发送的登录 cookie"

    candidates = ["https://cdn-a/live.flv", "https://cdn-b/live.flv"]
    responses = [Response([b"FLV\x01\x04\x00\x00\x00\x09"]), Response()]
    with mock.patch.object(bili, "_app_play_urls", new=lambda room, qn, codec: ([candidates[0]], 250)), \
         mock.patch.object(bili, "_web_play_urls", new=lambda room, qn, codec: ([candidates[1]], 250)), \
         mock.patch.object(bili.requests, "get", side_effect=responses):
        selected = bili.play_url("1001", 250)
    assert selected == (candidates[1], 250, "web", dict(bili.STREAM_WEB)), \
        "App 的纯音频 FLV 应继续尝试有视频的备用通道"
    assert all(response.closed for response in responses)

    # 两个 FLV 通道均只有声音时，仍有同编码的 HLS 可以观看。
    audio = b"FLV\x01\x04\x00\x00\x00\x09"
    hls_payload = {"data": {"playurl_info": {"playurl": {"stream": [{
        "protocol_name": "http_hls", "format": [{"format_name": "fmp4", "codec": [{
            "codec_name": "avc", "base_url": "/live.m3u8", "current_qn": 10000,
            "url_info": [{"host": "https://hls.example.test", "extra": ""}],
        }]}],
    }]}}}}
    with mock.patch.object(bili, "_app_play_urls", new=lambda room, qn, codec: ([candidates[0]], 250)), \
         mock.patch.object(bili, "_web_play_urls", new=lambda room, qn, codec: ([candidates[1]], 250)), \
         mock.patch.object(bili, "_app_play_info", return_value=hls_payload["data"]["playurl_info"]["playurl"]), \
         mock.patch.object(bili.requests, "get", side_effect=[
             Response([audio]), Response([audio]), Response([b"#EXTM3U\n"])]):
        hls = bili.play_url("1001", 250)
    assert hls == ("https://hls.example.test/live.m3u8", 10000, "app-hls-avc", dict(bili.STREAM_APP)), \
        "HLS 回退需保留真实编码、画质和请求头"

    app_payload = {"data": {"playurl_info": {"playurl": {"stream": [{
        "protocol_name": "http_stream", "format": [{"codec": [{
            "base_url": "/live.flv", "current_qn": 250,
            "url_info": [{"host": "https://cdn-a", "extra": ""},
                         {"host": "https://cdn-b", "extra": ""}],
        }]}],
    }]}}}}
    with mock.patch.object(bili.requests, "get", return_value=JsonResponse(app_payload)):
        assert bili._app_play_urls("1001", 250) == (candidates, 250)

    web_payload = {"code": 0, "data": {"current_qn": 250, "durl": [{
        "url": candidates[0], "backup_url": [candidates[1]],
    }]}}
    with mock.patch.object(bili.requests, "get", return_value=JsonResponse(web_payload)):
        assert bili._web_play_urls("1001", 250) == (candidates, 250)

    with mock.patch.object(bili, "_app_play_urls", return_value=(candidates, 250)), \
         mock.patch.object(bili, "_web_play_urls", side_effect=AssertionError("不应退回 web")), \
         mock.patch.object(bili, "_fetchable", return_value=True) as fetch:
        first = bili.play_url("1001", 250, source_offset=0)
        second = bili.play_url("1001", 250, source_offset=1)
    assert first[0] == "https://cdn-a/live.flv"
    assert second[0] == "https://cdn-b/live.flv", "重取流应试另一条 CDN"
    assert fetch.call_count == 2

    with mock.patch.object(bili, "_app_play_urls", return_value=(candidates, 250)), \
         mock.patch.object(bili, "_web_play_urls", side_effect=AssertionError("不应退回 web")), \
         mock.patch.object(bili, "_fetchable", side_effect=[False, True]) as fetch:
        fallback = bili.play_url("1001", 250)
    assert fallback[0] == "https://cdn-b/live.flv"
    assert fetch.call_count == 2, "第一条 CDN 不通时应试同通道备用地址"

    resolver = bili.StreamResolver("1001", 250, source_offset=1)
    with mock.patch.object(bili, "play_url", return_value=(
            "https://cdn-b/live.flv", 250, "app", bili.STREAM_APP)) as play, \
         mock.patch.object(bili, "room_quality_options", return_value=[]):
        resolver.run()
    assert play.call_args.kwargs["source_offset"] == 1, \
        "取流线程必须把轮换序号传给地址选择逻辑"
    print("取流探测、CDN 轮换与备用地址：通过")


if __name__ == "__main__":
    main()

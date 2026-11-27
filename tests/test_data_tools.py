"""Contract tests for data tools. Provider HTTP is simulated; no API credentials required."""
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from xml.etree import ElementTree as ET
import json
import unittest
from unittest.mock import patch
from urllib.parse import unquote

import httpx

from data_tools import DataService


def candidate(label, lat, lon):
    return {"address":{"freeformAddress":label}, "position":{"lat":lat,"lon":lon}}


class DataContract(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.fixtures = {}
        self.now = datetime(2026, 11, 20, 18, tzinfo=timezone.utc)
        def serve(request):
            self.requests.append(request)
            label = request.url.host
            self.assertIn(label, self.fixtures, f"Unexpected request to {label}")
            fixture = self.fixtures[label]
            status, payload = fixture(request) if callable(fixture) else fixture
            if isinstance(payload,bytes):return httpx.Response(status,content=payload)
            return httpx.Response(status, json=payload)
        self.client = httpx.Client(transport=httpx.MockTransport(serve))
        self.addCleanup(self.client.close)
        self.service = DataService(self.client, lambda:self.now, lambda provider:"fixture-token-private")

    def run_tool(self, name, **arguments):
        return self.service.execute(name, arguments)

    def resolve(self, *items, query="Rosario", **arguments):
        self.fixtures["api.tomtom.com"] = (200, {"results":items})
        return self.run_tool("resolve_place", query=query, **arguments)

    def forecast(self, lo=0):
        self.fixtures["api.open-meteo.com"] = (200, {
            "current":{"temperature_2m":0,"time":"2026-11-20T08:00"},
            "timezone":"America/Argentina/Cordoba",
            "daily":{"time":["2026-11-20","2026-11-21"],
                     "temperature_2m_min":[lo,-2],"temperature_2m_max":[8,5],
                     "precipitation_probability_max":[0,55]}})

    def test_unspecified_kind_does_not_append_buenos_aires_to_rosario(self):
        self.resolve(candidate("Rosario, Santa Fe",-32.95,-60.64))
        self.assertNotIn("Buenos Aires", unquote(str(self.requests[0].url)))

    def test_candidate_choice_prevents_weather_until_selected(self):
        self.forecast()
        choices=self.resolve(candidate("San Martín, Mendoza",-33.08,-68.47),
                             candidate("San Martín, Buenos Aires",-34.58,-58.53),query="San Martín",kind="city")
        self.assertEqual(choices["status"],"needs_choice")
        self.assertEqual(len(choices["choices"]),2)
        selected=choices["choices"][1]
        self.assertEqual(self.run_tool("get_weather",place_id=selected["place_id"])["code"],"resolve_place")
        self.assertEqual(len(self.requests),1)
        self.assertEqual(self.run_tool("select_place",place_id=selected["place_id"])["announce_place"],selected["label"])
        weather=self.run_tool("get_weather",place_id=selected["place_id"],day_offset=1)
        self.assertEqual(weather["status"],"ok")
        self.assertEqual(self.requests[-1].url.params["latitude"],"-34.58")
        self.assertEqual(weather["place"]["label"],selected["label"])
        self.assertIn("55%",weather["summary"])
        self.assertNotIn("Temperatura actual",str(weather["fields"]))

    def test_poi_uses_fuzzy_and_explicit_city(self):
        result=self.resolve(candidate("Monumento local, Rosario",-32.95,-60.64),query="Monumento",kind="poi",city="Rosario")
        self.assertEqual(result["status"],"ok")
        req=self.requests[0]
        self.assertIn("/search/2/search/",req.url.path)
        self.assertIn("Rosario",req.url.path)
        self.assertNotIn("Buenos Aires",req.url.path)

    def test_zeros_valid_for_weather_and_cached_until_ttl(self):
        self.forecast()
        with patch("data_tools.time.monotonic", return_value=3000) as monotonic:
            place=self.resolve(candidate("Rosario",-32.95,-60.64),kind="city")["place"]["place_id"]
            result=self.run_tool("get_weather",place_id=place)
            self.assertIn("0%",result["summary"])
            self.assertIn("0 °C",str(result["fields"]))
            self.assertTrue(self.run_tool("get_weather",place_id=place)["cached"])
            monotonic.return_value+=181
            self.assertFalse(self.run_tool("get_weather",place_id=place).get("cached",False))
            self.assertEqual(len(self.requests),3)

    def test_expired_location_cannot_be_served_from_weather_cache(self):
        self.forecast()
        with patch("data_tools.time.monotonic",return_value=5000) as monotonic:
            place=self.resolve(candidate("Rosario",-32.95,-60.64),kind="city")["place"]["place_id"]
            monotonic.return_value+=7199
            self.assertEqual(self.run_tool("get_weather",place_id=place)["status"],"ok")
            monotonic.return_value+=3
            self.assertEqual(self.run_tool("get_weather",place_id=place).get("code"),"resolve_place")
            self.assertEqual(len(self.requests),2)

    def test_unavailable_temperature_is_not_spoken_as_none(self):
        self.forecast(lo=None)
        place=self.resolve(candidate("Rosario",-32.95,-60.64),kind="city")["place"]["place_id"]
        self.assertNotIn("None",self.run_tool("get_weather",place_id=place)["summary"])

    def test_finnhub_zero_price_is_not_a_quote_and_zero_change_is_valid(self):
        host="finnhub.io"
        self.fixtures[host]=(200,{"c":0,"t":123})
        self.assertEqual(self.run_tool("get_stock",symbol="SPY",include_news=False)["status"],"error")
        self.fixtures[host]=(200,{"c":400,"t":123,"dp":0,"d":0})
        result=self.run_tool("get_stock",symbol="SPY",include_news=False)
        self.assertEqual(result["provider_time"],123)
        self.assertIn("ETF",result["attribution"])
        self.assertTrue(any(f["value"]=="0" for f in result["fields"]))

    def test_unusable_crypto_quote(self):
        self.fixtures["api.coingecko.com"]=(200,{"bitcoin":{"usd":0,"last_updated_at":123}})
        self.assertEqual(self.run_tool("get_crypto",ids=["bitcoin"])["status"],"error")

    def test_empty_fx_rates(self):
        self.fixtures["api.frankfurter.dev"]=(200,{"rates":{},"date":"2026-11-20"})
        self.assertEqual(self.run_tool("get_exchange_rates",base="USD",symbols=["EUR"])["status"],"error")

    def test_malformed_json_shape_returns_structured_error(self):
        self.fixtures["api.tomtom.com"]=(200,[])
        self.assertEqual(self.run_tool("resolve_place",query="Rosario",kind="city")["status"],"error")

    def test_dollar_one_sided_quote_remains_identifiable(self):
        self.fixtures["dolarapi.com"]=(200,{"nombre":"Tarjeta","compra":None,"venta":1500,"fechaActualizacion":"2026-11-20T14:00:00Z"})
        result=self.run_tool("get_dollar",kind="tarjeta")
        self.assertEqual(result["status"],"ok")
        self.assertEqual(result["rows"][0][2],1500)
        self.assertNotEqual(result["rows"][0][1],0)

    def test_provider_error_redaction_and_no_cache_on_error(self):
        self.fixtures["finnhub.io"]=(429,{"error":"https://host/?token=fixture-token-private"})
        for _ in range(2):
            result=self.run_tool("get_stock",symbol="TSLA",include_news=False)
            self.assertNotIn("fixture-token-private",json.dumps(result))
            self.assertEqual(result["code"],"rate_limit")
        self.assertEqual(len(self.requests),2)

    def feed(self, entries):
        root=ET.Element("rss"); channel=ET.SubElement(root,"channel")
        for i,(title,age) in enumerate(entries):
            item=ET.SubElement(channel,"item")
            values={"title":title,"pubDate":format_datetime(self.now-timedelta(hours=age)) if age is not None else "invalid-date",
                    "link":f"https://publisher.example/{i}","source":"Medio"}
            for key,value in values.items():ET.SubElement(item,key).text=value
        self.fixtures["news.google.com"]=(200,ET.tostring(root))

    def test_rss_orders_deduplicates_and_bounds_dates(self):
        self.feed([("Más antigua - B",30),("Novedad - Medio",2),("Novedad - Otro medio",3),
                   ("Fuera de rango",200),("Titular futuro",-48)])
        result=self.run_tool("get_news",query="ciencia",days=3)
        self.assertEqual([i["title"] for i in result["items"]],["Novedad - Medio","Más antigua - B"])
        self.assertEqual(result["source"],"Google News RSS")
        self.assertEqual(len(self.requests),1)

    def test_malformed_rss_item_does_not_discard_valid_items(self):
        self.feed([("Nota válida",2),("Fecha ilegible",None),("Segunda válida",3)])
        self.service.key_lookup=lambda provider:None
        result=self.run_tool("get_news",query="ciencia",days=3)
        self.assertEqual(result["status"],"ok")
        self.assertEqual([i["title"] for i in result["items"]],["Nota válida","Segunda válida"])
        self.assertEqual(result["source"],"Google News RSS")

    def test_broken_rss_document_uses_gnews_fallback(self):
        self.fixtures["news.google.com"]=(200,b"<rss>broken")
        self.fixtures["gnews.io"]=(200,{"articles":[{"publishedAt":"2026-11-20T08:30:00Z","title":"Buen día",
            "url":"https://publisher.example/actualidad","source":{"name":"Medio"}}]})
        result=self.run_tool("get_news",query="Rosario")
        self.assertEqual(result["source"],"GNews")
        self.assertEqual(result["items"][0]["title"],"Buen día")
        self.assertNotIn("fixture-token-private",json.dumps(result))

    def test_traffic_bbox_longitude_first_and_partial_failures(self):
        place=self.resolve(candidate("Rosario",-32.95,-60.64),kind="city")["place"]["place_id"]
        def traffic(req):
            if "incidentDetails" in req.url.path:
                bbox=list(map(float,req.url.params["bbox"].split(",")))
                for value,expected in zip(bbox,[-60.66,-32.97,-60.62,-32.93]):
                    self.assertAlmostEqual(value,expected)
                return 429,{"error":"fixture-token-private"}
            self.assertEqual(req.url.params["point"],"-32.95,-60.64")
            return 200,{"flowSegmentData":{"currentSpeed":0,"freeFlowSpeed":50,"roadClosure":True,
                                          "currentTravelTime":120,"freeFlowTravelTime":80}}
        self.fixtures["api.tomtom.com"]=traffic
        result=self.run_tool("get_traffic",place_id=place)
        self.assertEqual(result["status"],"ok")
        self.assertTrue(result["warnings"])
        self.assertIn("40 s",[f["value"] for f in result["fields"]])
        self.assertIn("0 km/h",[f["value"] for f in result["fields"]])
        self.assertFalse(any("Incidentes en" in f["label"] for f in result["fields"]))
        self.assertNotIn("fixture-token-private",json.dumps(result))

    def test_traffic_names_reported_endpoints_and_omits_future(self):
        place=self.resolve(candidate("Localidad", -32.95,-60.64),kind="city")["place"]["place_id"]
        def traffic(req):
            if "incidentDetails" not in req.url.path:
                return 503,{}
            for field in ("events{description}","from,to,roadNumbers","delay","timeValidity"):
                self.assertIn(field,req.url.params["fields"])
            self.assertEqual(req.url.params["timeValidityFilter"],"present")
            return 200,{"incidents":[{"properties":p} for p in [
                {"iconCategory":6,"from":"Puente Norte","to":"Cruce Sur","roadNumbers":["RN 1"],"events":[{"description":"Tránsito lento"}],"delay":0},
                {"iconCategory":8,"events":[],"delay":0},{"iconCategory":9,"timeValidity":"future","from":"Calle futura"}]]}
        self.fixtures["api.tomtom.com"]=traffic
        result=self.run_tool("get_traffic",place_id=place)
        self.assertEqual(len(result["rows"]),2)
        self.assertEqual(result["rows"][0],["Tránsito lento","RN 1 · Desde Puente Norte · Hasta Cruce Sur","0 s","Sin dato"])
        self.assertEqual(result["rows"][1][1:3],["Ubicación vial no informada","Sin dato"])
        self.assertIn("Puente Norte",result["summary"])
        self.assertNotIn("Calle futura",json.dumps(result,ensure_ascii=False))
        self.assertTrue(result["warnings"])

    def test_crypto_demo_key_is_header_and_nulls_remain_unknown(self):
        self.fixtures["api.coingecko.com"]=(200,{"bitcoin":{"usd":83500,"usd_24h_change":None,"last_updated_at":None},
                                                 "ethereum":{"usd":None}})
        result=self.run_tool("get_crypto",ids=["bitcoin","ethereum"])
        request=self.requests[0]
        self.assertEqual(request.headers["x-cg-demo-api-key"],"fixture-token-private")
        self.assertNotIn("fixture-token-private",str(request.url))
        self.assertEqual(len(result["rows"]),1)
        self.assertEqual(result["rows"][0],["bitcoin",83500,"USD",None,"No informada"])

    def test_nasa_permalink_is_not_image_and_date_is_respected(self):
        image={"date":"2026-11-19","title":"Fixture","media_type":"image","permalink":"https://science.nasa.gov/item/",
               "hdurl":"https://science.nasa.gov/images/test.jpg","credit":"Fixture credit","explanation":"Descripción."}
        video={**image,"date":"2026-11-20","media_type":"iframe"}
        self.fixtures["science.nasa.gov"]=(200,[{**image,"date":"2026-11-21"},video,image])
        result=self.run_tool("get_astronomy")
        self.assertEqual(result['image']['role'],'poster')
        self.assertEqual(result['image']['url'],image['hdurl'])
        self.assertIsNone(result['video'])
        self.assertEqual(result["items"][0]["url"],video["permalink"])
        self.fixtures["science.nasa.gov"]=(200,image)
        result=self.run_tool("get_astronomy",date="2026-11-19")
        self.assertTrue(self.requests[-1].url.path.endswith("/261119"))
        self.assertEqual(result["image"]["url"],image["hdurl"])
        self.assertEqual(result["image"]["credit"],"Fixture credit")

    def test_nasa_video_and_poster_come_from_api_without_executing_html(self):
        self.fixtures['science.nasa.gov']=(200,{'date':'2026-11-20','title':'Video APOD','media_type':'video',
            'hdurl':'https://assets.science.nasa.gov/preview.png','copyright':'NASA fixture',
            'basic_html':'<script>throw new Error("never execute")</script><video><source src="https://assets.science.nasa.gov/movie.mp4" type="video/mp4"></video>'})
        result=self.run_tool('get_astronomy')
        self.assertEqual(result['image']['role'],'poster')
        self.assertEqual(result['video'],{'url':'https://assets.science.nasa.gov/movie.mp4','date':'2026-11-20'})
        self.assertEqual(result['image']['credit'],'NASA fixture')
        self.assertEqual(len(self.requests),1,'showing the card does not download its video')
        self.assertNotIn('<script>',json.dumps(result))

    def test_nasa_untrusted_media_and_iframes_are_not_exposed_as_playable(self):
        self.fixtures['science.nasa.gov']=(200,{'date':'2026-11-20','media_type':'iframe',
            'hdurl':'https://nasa.gov.attacker.example/preview.jpg',
            'basic_html':'<iframe src="https://video.example/player"></iframe><video src="https://nasa.gov.attacker.example/evil.mp4"></video>'})
        result=self.run_tool('get_astronomy')
        self.assertIsNone(result['image']);self.assertIsNone(result['video'])
        self.assertIn('no ofrece un video reproducible',result['notice'])

    def test_nasa_video_download_uses_confirmed_date_and_enforces_mime_size_and_redirects(self):
        def serve(request):
            self.requests.append(request)
            if request.url.host=='science.nasa.gov':
                return httpx.Response(200,json={'date':'2026-11-20','media_type':'video','basic_html':'<video src="https://assets.science.nasa.gov/movie.mp4"></video>'})
            self.assertEqual(request.url.host,'assets.science.nasa.gov')
            return self.media_response()
        client=httpx.Client(transport=httpx.MockTransport(serve),follow_redirects=True)
        self.addCleanup(client.close);self.service.client=client
        self.media_response=lambda:httpx.Response(200,content=b'video-bytes',headers={'Content-Type':'video/mp4'})
        self.assertEqual(self.service.astronomy_video('2026-11-20'),(b'video-bytes','video/mp4'))
        from data_tools import DataError
        for response in [httpx.Response(302,headers={'Location':'https://attacker.example/movie.mp4'}),
                         httpx.Response(200,content=b'<html>not video</html>',headers={'Content-Type':'text/html'}),
                         httpx.Response(200,content=b'123456789',headers={'Content-Type':'video/mp4'})]:
            self.media_response=lambda response=response:response
            with patch('data_tools.MAX_ASTRONOMY_VIDEO_BYTES',8),self.assertRaises(DataError):
                self.service.astronomy_video('2026-11-20')
        class Chunks(httpx.SyncByteStream):
            def __iter__(self):yield b'1234';yield b'56789'
        self.media_response=lambda:httpx.Response(200,stream=Chunks(),headers={'Content-Type':'video/mp4'})
        with patch('data_tools.MAX_ASTRONOMY_VIDEO_BYTES',8),self.assertRaises(DataError):
            self.service.astronomy_video('2026-11-20')


if __name__=="__main__":
    unittest.main()

# 檔案名稱: youtube_utils.py
import requests
import json
import urllib.parse

class CustomYoutubeSearch:
    def __init__(self, search_terms: str, max_results=None):
        self.search_terms = search_terms
        self.max_results = max_results
        self.videos = self._search()

    def _search(self):
        # 設定搜尋參數：強制指定繁體中文 (hl=zh-TW) 與台灣地區 (gl=TW)
        params = {
            "search_query": self.search_terms,
            "hl": "zh-TW",
            "gl": "TW"
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "zh-TW,zh;q=0.9"
        }

        try:
            # 發送請求
            response = requests.get(
                "https://www.youtube.com/results", 
                params=params, 
                headers=headers, 
                timeout=10
            )
            response.raise_for_status()
            return self._parse_html(response.text)
        except Exception as e:
            print(f"搜尋發生錯誤: {e}")
            return []

    def _parse_html(self, html):
        results = []
        try:
            start = (html.index("ytInitialData") + len("ytInitialData") + 3)
            end = html.index("};", start) + 1
            json_str = html[start:end]
            data = json.loads(json_str)
            
            section_list = data["contents"]["twoColumnSearchResultsRenderer"]["primaryContents"]["sectionListRenderer"]["contents"]
            for section in section_list:
                if "itemSectionRenderer" in section:
                    for item in section["itemSectionRenderer"]["contents"]:
                        if "videoRenderer" in item:
                            video_data = item["videoRenderer"]
                            res = {}
                            res["id"] = video_data.get("videoId", None)
                            res["title"] = video_data.get("title", {}).get("runs", [{}])[0].get("text", None)
                            results.append(res)
        except Exception as e:
            print(f"解析 HTML 結構錯誤: {e}")
        
        if self.max_results and len(results) > self.max_results:
            return results[:self.max_results]
        return results
        
    def to_dict(self):
        return self.videos
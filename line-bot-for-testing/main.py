from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextSendMessage, FollowEvent, StickerSendMessage, FlexSendMessage, ImageSendMessage
import json
import os
from random import sample, randint
import xlrd
from bs4 import BeautifulSoup
import urllib
from fake_useragent import UserAgent
import time

app = Flask(__name__)
# line api 基本資訊
line_bot_api = LineBotApi(os.environ["ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["SECRET"])
# 儲存個人答題資訊
# state: user 狀態(get_question, get_cnt, answer, get_scope)
# mode: 測驗模式(default, wrong_question)
# title: 範圍標題
# chinese: 單字的中文列表
# english: 單字英文列表
# sentence: 單字句子
# ans: 答案列表
# order: 題目順序
# num: 第order[num]題
# cnt: 該範圍的總題目數/已選擇之題數
# correct_num: 已答對題數
vocabulary_state = {}

# line bot 初始化
@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print(
            "Invalid signature. Please check your channel access token/channel secret."
        )
        abort(400)

    return 'OK'
# 寫入錯題紀錄
def write_wrong_question(user_id, title, chinese, english):
    # 開啟原本紀錄
    try:
        with open(os.path.join("history", user_id + ".json"), "r") as f:
            obj = json.load(f)
    except:
        obj = {}
    # 同範圍已有錯題直接新增，否則建立新的範圍
    try:
        obj[title].append([chinese, english])
    except:
        obj[title] = [[chinese, english]]
    # 寫入
    json.dump(obj, open(os.path.join("history", user_id + ".json"), "w"), indent = 4)

# 讀取錯題中/英文
def read_wrong_question(user_id, title):
    value = {"have_history": True, "chinese": [], "english": []}
    # 嘗試開啟錯題紀錄
    try:
        with open(os.path.join("history", user_id + ".json"), "r") as f:
            obj = json.load(f)
        obj = obj[title]
        for i in obj:
            value["chinese"].append(i[0])
            value["english"].append(i[1])
    # 找不到紀錄
    except:
        value["have_history"] = False
    return value

# 將單字從錯題紀錄刪除
def del_wrong_question(user_id, title, chinese, english):
    # 讀檔
    with open(os.path.join("history", user_id + ".json"), "r") as f:
        obj = json.load(f)
    # 找出題目在清單中位置並刪除
    id = obj[title].index([chinese, english])
    # 範圍內已無錯題 直接刪除此項目
    if len(obj[title]) == 1: del obj[title]
    # 刪除已答對之單字
    else: del obj[title][id]
    # 寫檔
    json.dump(obj, open(os.path.join("history", user_id + ".json"), "w"), indent = 4)

# 取得網站html
def getHTML(url):
    # 取得隨機ip位置(user agent)
    headers = {'User-Agent': 'User-Agent:' + UserAgent().random}
    r = urllib.request.Request(url, headers=headers)
    # 嘗試取得html
    try:
        return urllib.request.urlopen(r).read()
    except:
        time.sleep(1)
        return getHTML(url)

# 取得例句
def get_sentence(word):
    # 為片語(不找例句))
    if " " in word:
        # 只留頭尾提示
        v = list(word)
        for i in range(1, len(word) - 1):
            if v[i] != " ": v[i] = "_"
        answers = [word]
        sentences = ["".join(v)]
    else:
        try:
            # 例句之html
            soup_for_sentence = BeautifulSoup(getHTML("https://dictionary.cambridge.org/dictionary/english/" + word), "html.parser")
            # 單字變化(複數、過去式...)之html
            soup_for_changing = BeautifulSoup(getHTML("https://www.dictionary.com/browse/" + word), "html.parser")
        except:
            # 無法取得html->直接回傳題目
            v = list(word)
            for i in range(1, len(word) - 1):
                if v[i] != " ": v[i] = "_"
            answers = [word]
            sentences = ["".join(v)]
            return sentences, answers
        # 尋找例句
        sentences_html = soup_for_sentence.find_all(class_ = "eg deg") + soup_for_sentence.find_all(class_ = "deg")
        # 找單字變化
        if soup_for_changing.find_all(class_ = "css-h12q9j eejl9t60") != []:
            changing = soup_for_changing.find_all(class_ = "css-h12q9j eejl9t60")
        # 找不到其單字變化->直接使用原型
        else:   
            changing = soup_for_changing.find_all(class_ = "css-1jwcxx3 e12fnee31")
        # 找不到此單字->直接使用輸入的單字
        if soup_for_changing.find("h1").text != word.lower():
            changing = [word]
        changing.reverse()
        sentences = []
        answers = []
        # 處理每一個例句
        for sentence_html in sentences_html:
            sentence = ""
            ans = ""
            # 將零散html訊息合併成完整句子
            for j in sentence_html.children:
                try:
                    sentence += j.text
                except:
                    sentence += j
            # 嘗試單字的不同變化
            for i in changing:
                try:
                    i = i.contents[0].text
                except:
                    pass
                # 找尋句子中的單字
                if i in sentence and (sentence.find(i) + len(i) < len(sentence) and not sentence[sentence.find(i) + len(i)].isalnum()):
                    sentence = sentence.replace(i, (i[0] + "_" * (len(i) - 2) + i[-1]))
                    ans = i
                # 將字首改為大寫 再次尋找並修改
                i = i[0].upper() + i[1:]
                if i in sentence and (sentence.find(i) + len(i) < len(sentence) and not sentence[sentence.find(i) + len(i)].isalnum()):
                    sentence = sentence.replace(i, (i[0] + "_" * (len(i) - 2) + i[-1]))
                    ans = i
            # 句子中找不到單字
            if ans == "": continue
            sentence = sentence.strip(" ").strip("\n").strip(" ")
            print(sentence)
            sentences.append(sentence)
            answers.append(ans)
        # 找不到例句 直接產生題目(留字首字尾)
        if sentences == []:
            v = list(word)
            for i in range(1, len(v) - 1):
                if v[i] != " ": v[i] = "_"
            sentences.append("".join(v))
            answers.append(word)
    return sentences, answers


# 單字測驗模式
def vocabulary(event):
    user_id = event.source.user_id
    # 進入考單字模式 詢問考試範圍
    if not user_id in vocabulary_state:
        # 初始化資料
        vocabulary_state[user_id] = {"state": "get_question", "title": "", "chinese": [], "english": [], "sentence": [], "ans": [],  "order": [], "num": -1, "cnt": -1, "correct_num": 0}
        # 設定測驗模式
        if event.message.text == "單字":
            vocabulary_state[user_id]["mode"] = "default"
            actions = []
            # 讀取目前有的範圍
            word = "請輸入考試範圍\n目前有的題目:"
            for i in os.listdir("question"):
                actions.append({
                        "type": "button",
                        "style": "link",
                        "height": "sm",
                        "action": {
                        "type": "message",
                        "label": i[0:-5],
                        "text": i[0:-5]
                        }
                })
                word += "\n" + i[0:-5]
            # 使用flex_template
            contents = {
                "type": "bubble",
                "hero": {
                    "type": "image",
                    "url": "https://s.yimg.com/ny/api/res/1.2/OEyrjkSv6JDNXf_eIgLwHA--/YXBwaWQ9aGlnaGxhbmRlcjt3PTY0MDtoPTQwMA--/https://s.yimg.com/os/creatr-uploaded-images/2021-02/572c4830-721d-11eb-bb63-96959c3b62f2",
                    "margin": "none",
                    "size": "full"
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                    {
                        "type": "text",
                        "text": "請選擇考試範圍",
                        "weight": "bold",
                        "size": "xl",
                        "style": "normal",
                        "decoration": "none"
                    },
                    {
                        "type": "text",
                        "text": "目前有的題目 :"
                    }
                    ]
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "contents": actions,
                    "flex": 0
                }
            }
            line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text = word, contents = contents))
            return
        else:
            vocabulary_state[user_id]["mode"] = "wrong_question"
            # 讀取錯題紀錄
            try:
                # 讀檔
                with open(os.path.join("history", user_id + ".json"), "r") as f:
                    obj = json.load(f)
                # 無錯題紀錄
                if len(obj.keys()) == 0:
                    word = "目前沒有錯題記錄喔!"
                    del vocabulary_state[user_id]
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(word))
                    return
                else:
                    word = "目前有的錯題範圍:"
                    actions = []
                    for i in obj.keys():
                        word += "\n" + i
                        actions.append({
                            "type": "button",
                            "style": "link",
                            "height": "sm",
                            "action": {
                            "type": "message",
                            "label": i,
                            "text": i
                            }
                        })
                    contents = {
                        "type": "bubble",
                        "hero": {
                            "type": "image",
                            "url": "https://images.chinatimes.com/newsphoto/2016-12-22/656/B18A00_P_01_02.jpg",
                            "margin": "none",
                            "size": "full"
                        },
                        "body": {
                            "type": "box",
                            "layout": "vertical",
                            "contents": [
                            {
                                "type": "text",
                                "text": "請選擇錯題範圍",
                                "weight": "bold",
                                "size": "xl",
                                "style": "normal",
                                "decoration": "none"
                            },
                            {
                                "type": "text",
                                "text": "目前有 :"
                            }
                            ]
                        },
                        "footer": {
                            "type": "box",
                            "layout": "vertical",
                            "spacing": "sm",
                            "contents": actions,
                            "flex": 0
                        }
                    }
                    line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text = word, contents = contents))
                    vocabulary_state[user_id]["state"] = "get_question"
                    return
            except:
                word = "目前沒有錯題紀錄喔!"
                del vocabulary_state[user_id]
                line_bot_api.reply_message(event.reply_token, TextSendMessage(word))
                return
    # 結束測驗模式
    if event.message.type == "text" and (event.message.text == "離開" or event.message.text == "結束"):
        del vocabulary_state[user_id]
        line_bot_api.reply_message(event.reply_token, TextSendMessage("已結束測驗模式"))
        return
    # 得到考試範圍
    if vocabulary_state[user_id]["state"] == "get_question":
        if event.message.type == "text":
            # 錯題模式 直接讀取該範圍題目
            if vocabulary_state[user_id]["mode"] == "wrong_question":
                try:
                    with open(os.path.join("history", user_id + ".json"), "r") as f:
                        obj = json.load(f)
                    obj = obj[event.message.text.upper()]
                    print(obj)
                    for i in obj:
                        vocabulary_state[user_id]["chinese"].append(i[0])
                        vocabulary_state[user_id]["english"].append(i[1])
                        vocabulary_state[user_id]["ans"].append(i[1])
                    vocabulary_state[user_id]["state"] = "get_cnt"
                    vocabulary_state[user_id]["title"] = event.message.text.upper()
                    vocabulary_state[user_id]["cnt"] = len(obj)
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(f"請輸入題數 目前有{len(obj)}題"))
                    return
                except:
                    line_bot_api.reply_message(event.reply_token, TextSendMessage("此範圍目前沒有錯題記錄"))
                    return
            # 預設模式 詢問課次/項目
            else:
                try:
                    with open(os.path.join("question", event.message.text.upper()) + ".json", "r") as f:
                        obj = json.load(f)
                    vocabulary_state[user_id]["title"] = event.message.text.upper()
                    vocabulary_state[user_id]["state"] = "get_scope"
                    if len(obj) > 1:
                        vocabulary_state[user_id]["state"] = "get_scope"
                        word = "請輸入課次/項目\n目前有:"
                        # 依序加入課次
                        actions = []
                        for i in sorted(obj.keys()):
                            word += "\n" + i
                            # 按鈕
                            actions.append({
                                "type": "button",
                                "style": "link",
                                "height": "sm",
                                "action": {
                                "type": "message",
                                "label": i,
                                "text": i
                                }
                            })
                        # 選單
                        contents = {
                            "type": "bubble",
                            "hero": {
                                "type": "image",
                                "url": "https://obs.line-scdn.net/0htFZvjvvQK2lnDz0y6yJUPl1ZKAZUYzhqAzl6aiRhdV5LPT42W280WkZYdF0fOmw3DmlhD0AHMFgfOWVvUm40/w644",
                                "margin": "none",
                                "size": "full"
                            },
                            "body": {
                                "type": "box",
                                "layout": "vertical",
                                "contents": [
                                {
                                    "type": "text",
                                    "text": "請選擇課次/項目",
                                    "weight": "bold",
                                    "size": "xl",
                                    "style": "normal",
                                    "decoration": "none"
                                },
                                {
                                    "type": "text",
                                    "text": "目前有 :"
                                }
                                ]
                            },
                            "footer": {
                                "type": "box",
                                "layout": "vertical",
                                "spacing": "sm",
                                "contents": actions,
                                "flex": 0
                            }
                        }
                        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text = word, contents = contents))
                        return
                    elif len(obj) == 0:
                        vocabulary_state[user_id]["state"] = "get_question"
                        line_bot_api.reply_message(event.reply_token, TextSendMessage("很抱歉，題庫尚未建立題目，請試試其他範圍"))
                        return
                except:
                    line_bot_api.reply_message(event.reply_token, TextSendMessage("找不到指定考試範圍題目，請再試一次"))
                    return
        else: 
            line_bot_api.reply_message(event.reply_token, TextSendMessage("請輸入考試範圍"))
            return
    # (default模式)得到考試課次/項目 詢問題目數
    if vocabulary_state[user_id]["state"] == "get_scope":
        with open(os.path.join("question", vocabulary_state[user_id]["title"]) + ".json", "r") as f:
            obj = json.load(f)
        # 取得特定課次的中文、英文
        try:
            if len(obj) > 1:
                obj = obj[event.message.text.upper()]
            else:
                obj = obj[list(obj.keys())[0]]
            for i in obj: 
                vocabulary_state[user_id]["chinese"].append(i[0])
                vocabulary_state[user_id]["english"].append(i[1])
                idx = randint(0, (len(i[2]) - 1))
                vocabulary_state[user_id]["sentence"].append(i[2][idx])
                vocabulary_state[user_id]["ans"].append(i[3][idx])
            vocabulary_state[user_id]["cnt"] = len(obj)
            vocabulary_state[user_id]["state"] = "get_cnt"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(f"請輸入題數\n總共有{len(obj)}題"))
            return
        except:
            line_bot_api.reply_message(event.reply_token, TextSendMessage("找不到指定課次/項目，請再試一次"))
            return

    # 得到題數
    if vocabulary_state[user_id]["state"] == "get_cnt":
        if not event.message.type == "text":
            line_bot_api.reply_message(event.reply_token, TextSendMessage("請輸入題數"))
            return
        elif not (event.message.text).isdigit() or int(event.message.text) <= 0:
            line_bot_api.reply_message(event.reply_token, TextSendMessage("請輸入大於0的阿拉伯數字"))
            return
        elif int(event.message.text) > vocabulary_state[user_id]["cnt"]:
            print(event.message.text)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(f"只有{vocabulary_state[user_id]['cnt']}題 請輸入小一點的數字"))
            return
        else:
            vocabulary_state[user_id]["order"] = sample(range(vocabulary_state[user_id]["cnt"]), int(event.message.text))
            vocabulary_state[user_id]["cnt"] = int(event.message.text)
            vocabulary_state[user_id]["state"] = "answer"
    # 作答中
    if vocabulary_state[user_id]["state"] == "answer":
        if event.message.type != "text": 
            line_bot_api.reply_message(event.reply_token, TextSendMessage("請以文字作答"))
            return
        vocabulary_state[user_id]["num"] += 1
        num = vocabulary_state[user_id]["num"]
        order = vocabulary_state[user_id]["order"]
        word = ""
        cnt = vocabulary_state[user_id]["cnt"]
        # 尚未開始作答
        if num == 0:
            word += f"共{str(cnt)}題 每題{str(100 // cnt )}分 送{str(100 % cnt)}分\n小提醒：輸入「離開」即可退出測驗模式\n--------------------\n"
        # 得到回答(第order[num - 1]題)
        else:
            ans = vocabulary_state[user_id]['ans'][order[num - 1]]
            # 答對
            if event.message.text.lower().strip() == ans.lower():
                word += "correct!\n"
                vocabulary_state[user_id]["correct_num"] += 1
                # 錯題模式中 刪除已答對題目
                if vocabulary_state[user_id]["mode"] == "wrong_question":
                    del_wrong_question(user_id, vocabulary_state[user_id]["title"], vocabulary_state[user_id]["chinese"][order[num - 1]], ans)
            # 答錯
            else:
                word += f"正確答案應該是 {ans}\n"
                # 記錄錯題
                if vocabulary_state[user_id]["mode"] != "wrong_question":
                    write_wrong_question(event.source.user_id, vocabulary_state[user_id]['title'], vocabulary_state[user_id]['chinese'][order[num - 1]], vocabulary_state[user_id]["english"][order[num - 1]])

        # 作答結束
        if num == cnt:
            word += f"--------------------\n測驗結束!\n總分:{str((100 // cnt) * vocabulary_state[user_id]['correct_num'] + (100 % cnt))}分"
            del vocabulary_state[user_id]
        else:
            # 取得題號
            i = order[num]
            # default題目
            if vocabulary_state[user_id]["mode"] != "wrong_question":
                word += f"{num + 1}. {vocabulary_state[user_id]['sentence'][i]} ({vocabulary_state[user_id]['chinese'][i]})" 
            else:
                v = list(vocabulary_state[user_id]["english"][i])
                for j in range(1, len(v) - 1):
                    if v[j] != " ": v[j] = "_"
                print(vocabulary_state[user_id]["chinese"], i)
                word += f"{num + 1}. {vocabulary_state[user_id]['chinese'][i]} {''.join(v)}"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(word))

# 上傳題庫         
def upload_file(event):
    upload_user_id = event.source.user_id
    line_bot_api.reply_message(event.reply_token, TextSendMessage("開始上傳!"))
    # 取得檔案與檔名
    content = line_bot_api.get_message_content(str(event.message.id))
    fileName = event.message.file_name.upper()
    # 下載題目
    with open(os.path.join("storage", fileName),
              "wb") as f:
        for chunk in content.iter_content():
            f.write(chunk)
    # 讀取xlsx檔
    xlsx = xlrd.open_workbook(os.path.join("storage", fileName)) 
    d = {} # 存放題目的dictionary
    print(xlsx.sheet_names())
    # 依序讀取每個工作表
    i = 0
    for sheet_name in list(xlsx.sheet_names()):
        sheet_name = sheet_name.upper()
        d[sheet_name] = []
        sheet = xlsx.sheets()[i]
        questions = sheet.nrows
        Chinese = sheet.col_values(0)
        English = sheet.col_values(1)
        for j in range(questions):
            # d[sheet_name].append([Chinese[j], English[j]])
            sentence, ans = get_sentence(English[j])
            d[sheet_name].append([Chinese[j], English[j], sentence, ans])
        i += 1
    # 將題目新增至現有的題庫中
    try:
        with open(os.path.join("question", fileName[:-5] + ".json"), "r") as f:
            obj = json.load(f)
    # 開新的題庫
    except:
        obj = {}
        print("open new file")
    print("已載入:")
    for i in d.keys():
        obj[i] = d[i]
        print(i, end = " ")
    print()
    # 將題目寫入json檔
    json.dump(d, open(os.path.join("question", fileName[:-5] + ".json"), "w"), indent = 4)
    line_bot_api.push_message(upload_user_id, TextSendMessage(f"已成功上傳{fileName.replace('XLSX', 'xlsx')}"))
        

@handler.add(MessageEvent)
def handle_message(event):
    print(event)
    with open("state.json", "r") as f:
        globals()["vocabulary_state"] = json.load(f)
    # 進入or已經在測驗模式
    if event.source.type == "user" and (event.source.user_id in vocabulary_state or (event.message.type == "text" and (event.message.text.strip() == "單字" or event.message.text.strip() == "錯題"))):
        vocabulary(event)
        json.dump(globals()["vocabulary_state"], open("state.json", "w"), indent = 4)
    # 使用說明
    elif event.message.type == "text" and event.message.text == "說明":
        line_bot_api.reply_message(event.reply_token, TextSendMessage("目前本機器人提供單字測驗服務\n單字：單字測驗\n錯題：複習錯題\n離開：結束測驗模式\n上傳格式：查看上傳題庫之格式\n\n有任何問題或bug請聯絡邱沐恩喔😊"))
    # 上傳格式說明
    elif event.message.type == "text" and event.message.text == "上傳格式":
        line_bot_api.reply_message(event.reply_token, ImageSendMessage(original_content_url = "https://dsm01pap004files.storage.live.com/y4mnTqgh48y71_PbmHLSDMMLrYt8JfcPb6Er5-q1Allc0CpYMWSS6vslxdTNRzrmP1dg2z6UOUCCgZ--SKdRTp4AI2WiSAS-AynWEtwzCaKGmbeoLvcOrzRAJnxZeg2CFjmb1IhG1YsfG0D1V29D8hYPV_MuZQi03C7qFVgpYHA1gf6FFCqVWKPf5ZWy-Ng1Cbz?width=1280&height=669&cropmode=none", preview_image_url = "https://dsm01pap004files.storage.live.com/y4mnTqgh48y71_PbmHLSDMMLrYt8JfcPb6Er5-q1Allc0CpYMWSS6vslxdTNRzrmP1dg2z6UOUCCgZ--SKdRTp4AI2WiSAS-AynWEtwzCaKGmbeoLvcOrzRAJnxZeg2CFjmb1IhG1YsfG0D1V29D8hYPV_MuZQi03C7qFVgpYHA1gf6FFCqVWKPf5ZWy-Ng1Cbz?width=1280&height=669&cropmode=none"))
        # line_bot_api.reply_message(event.reply_token, TextSendMessage("請使用excel格式(.xlsx)\n檔案名稱設為「考試範圍」\n工作表名稱設為「課次/項目」\n\n第一列請打中文\n第二列請打英文\n上傳後系統會自動從網路上抓例句"))
    # 檢查是否有人在答題
    elif event.message.type == "text" and event.source.type == "user" and event.message.text == "狀態" and event.source.user_id == "U3e5359d656fc6d1d6610ddcb33323bde":
        user = []
        with open("state.json", "r") as f:
            state = json.load(f)
        for i in state.keys():
            user.append(line_bot_api.get_profile(i).display_name)
        if len(user) == 0:
            line_bot_api.reply_message(event.reply_token, TextSendMessage("目前無人使用"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(f"目前{' '.join(user)}正在使用，共{len(user)}人"))
    # 上傳題庫
    elif event.message.type == 'file' and event.message.file_name[-4:] == "xlsx":
      	upload_file(event)
    elif event.message.type == "text":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(event.message.text))
    else:
        line_bot_api.reply_message(event.reply_token, StickerSendMessage("6362", "11087936"))

@handler.add(FollowEvent)
def handler_follow(event):
    print(event)
    with open("user.txt", "a") as f:
        content = line_bot_api.get_profile(event.source.user_id)
        f.write(content.display_name + " " + content.user_id + "\n")

@app.route("/")
def running():
    return "running"


if __name__ == "__main__":
    app.run(host="0.0.0.0")

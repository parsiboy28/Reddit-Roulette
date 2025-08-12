from flask import Flask, render_template, redirect, request, session, url_for
from  flask_session import Session
import requests
from uuid import uuid4
import urllib
from time import time
import json
from dotenv import load_dotenv
import os

load_dotenv()

CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
REDIRECT_URI = os.environ.get("REDIRECT_URI")
USER_AGENT = os.environ.get("USER_AGENT")

app = Flask(__name__)

app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = True
Session(app)



@app.route("/")
def index():
    #checks if user has access token
    if not session.get("access_token"):
        text = "<a href='%s'>Authenticate with reddit</a>"
        return text % make_authorization_url()

    #checks if the access token is expired
    now = time()
    if now - session["access_token_created_at"] > session["access_token_duration"]:
        refresh_access_token()
    

    
    return render_template("index.html", len=len)
    
@app.route("/subreddits", methods=["POST"])
def subreddits():
    subreddit = request.form.get("subreddit")
    session["content_type"] = request.form.get("content_type")

    if not subreddit:
        return render_template("index.html", error="Error: Enter Subreddit!")
    if session.get("content_type") == None:
        return render_template("index.html", error="Error: Choose Image/Video!")
    
    headers = {
        "User-Agent": USER_AGENT,
        "Authorization": f"bearer {session['access_token']}"
    }
    params={
        "q": subreddit,
        "limit": "4",
        "include_over_18": "on"
    }
    
    response = requests.get("https://oauth.reddit.com/subreddits/search/", headers=headers, params=params).json()["data"]["children"]

    subreddit_list = []
    for subreddit in response:
        subreddit_list.append({subreddit["data"]["display_name_prefixed"]: subreddit["data"]["public_description"]})
    
    indexed_subreddit_list = []
    for i, subreddit in enumerate(subreddit_list):
        letter = chr(97 + i)
        indexed_subreddit_list.append((letter, subreddit))

    return render_template("subreddits.html", subreddits=indexed_subreddit_list)

@app.route("/search", methods=["POST"])
def search():
    session["subreddit_name"] = request.form.get("subreddit")

    if session.get("content_type") == "image":
        return redirect("/image")
    
    elif session.get("content_type") == "video":
        return redirect("/video")

@app.route("/video")
def video():
    headers = {
        "User-Agent": USER_AGENT,
        "Authorization": f"bearer {session['access_token']}"
    }
    
    videos = []

    posts = requests.get(f"https://oauth.reddit.com/{session['subreddit_name']}/hot", headers=headers, params={"limit": "100"}).json()["data"]["children"]
    for post in posts:
        #for normal videos
        if post["data"]["is_video"] == True:
            videos.append({
                "title": post["data"].get("title", " "),
                "url": post["data"]["media"]["reddit_video"]["fallback_url"],
                "duration": post["data"]["media"]["reddit_video"]["duration"]
                })
        #for other type of videos ;)
        elif post["data"].get("media") is not None:
            media = post["data"].get("media", {})
            
            if media.get("type") == "redgifs.com":
                preview = post["data"].get("preview", {})
                redgif = preview.get("reddit_video_preview", {})
                url = redgif.get("fallback_url")
                duration = redgif.get("duration")
                
                if url and duration:
                    videos.append({
                        "title": post["data"].get("title", " "),
                        "url": url,
                        "duration": duration
                    })
    if not videos:
        return render_template("error.html", error="Sorry this subreddit doesn't have any videos:(")
    
    return render_template("video.html", videos=videos)

@app.route("/image")
def image():
    headers = {
        "User-Agent": USER_AGENT,
        "Authorization": f"bearer {session['access_token']}"
    }

    posts = requests.get(f"https://oauth.reddit.com/{session['subreddit_name']}/hot", headers=headers, params={"limit": "100"}).json()["data"]["children"]
    images = []

    for post in posts:
        if not post["data"].get("is_video") and "preview" in post["data"].keys():
            if "url_overridden_by_dest" in post["data"].keys() and post["data"]["url_overridden_by_dest"].endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".avif")):
                images.append({
                    "title": post["data"]["title"],
                    "url": post["data"]["url_overridden_by_dest"].replace("&amp;", "&")
                    })
        
            
    if not images:
        return render_template("error.html", error="Sorry this page doesn't have any images!")
    


    return render_template("image.html", images=images, index_len=len(images))


def make_authorization_url():
    state = str(uuid4())
    session["oauth_state"] = state

    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "state": state,
        "redirect_uri": REDIRECT_URI,
        "duration": "permanent",
        "scope": "read"
    }

    url = "https://www.reddit.com/api/v1/authorize?" + urllib.parse.urlencode(params)
    return url

#makes the access token
@app.route("/callback")
def callback():
    CODE = request.args.get("code")
    new_state = request.args.get("state")

    #check if the retrieved state is the same as the initialized state to prevent SCRF attacks
    if new_state != session.get("oauth_state"):
        return "Error: state mismatch, possible SCRF attack!"
    
    client_auth = requests.auth.HTTPBasicAuth(CLIENT_ID, CLIENT_SECRET)
    headers = {
        "User-Agent": "Web's API/0.1 by mr_bloebi"
    }
    post_data = {
            "grant_type": "authorization_code",
            "code": CODE,
            "redirect_uri": REDIRECT_URI
            }
    
    token_request = requests.post("https://www.reddit.com/api/v1/access_token", auth=client_auth, data=post_data, headers=headers)

    session["access_token"] = token_request.json()["access_token"]
    session["refresh_token"] = token_request.json().get("refresh_token")

    session["access_token_created_at"] = time()
    session["access_token_duration"] = 86400

    return redirect("/")

#refreshes the access token
def refresh_access_token():
    client_auth = requests.auth.HTTPBasicAuth(CLIENT_ID, CLIENT_SECRET)
    headers = {
        "User-Agent": USER_AGENT
    }
    post_data = {
        "grant_type": "refresh_token",
        "refresh_token": session["refresh_token"]
    }

    token_request = requests.post("https://www.reddit.com/api/v1/access_token", data=post_data, auth=client_auth, headers=headers)

    session["access_token"] = token_request.json()["access_token"]

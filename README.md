# Facebucket 

Require adapted version of fbchat 

```
pip install git+https://github.com/carpedm20/fbchat.git
```

Make following changes to `session.py`

Remove 
```diff
- if len(define_splits) > 2: raise _exception.ParseError("Found too many ServerJSDefine", data=define_splits)
```

Alter 
```diff
SERVER_JS_DEFINE_REGEX = re.compile(
-    r'(?:"ServerJS".{,100}\.handle\({.*"define":)|(?:require\("ServerJSDefine"\)\)?\.handleDefines\()'
+    r'(?:"ServerJS".{,100}\.handle\({.*"define":)'
+    r'|(?:ServerJS.{,100}\.handleWithCustomApplyEach\(ScheduledApplyEach,{.*"define":)'
+    r'|(?:require\("ServerJSDefine"\)\)?\.handleDefines\()'
)

-   r = session.get(prefix_url("/"), allow_redirects=False)
+   r = session.get(prefix_url("/"), allow_redirects=True)
```

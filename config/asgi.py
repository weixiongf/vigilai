"""ASGI 入口，集成 Django + Channels WebSocket.

注意: 生产环境强烈建议把 /static/ 交给 nginx / whitenoise 之类的专用静态文件
服务来托管. 这里之所以在 ASGI 层挂上 ASGIStaticFilesHandler, 是因为本项目
启动脚本 start.bat 用 daphne 替代了 runserver (为了让 SSE 真流式生效),
而 daphne 不像 runserver 那样自带开发期 /static/ 路由——必须在 ASGI 层
显式包装一层 staticfiles handler, 否则 DEBUG 模式下浏览器加载
/static/css/app.css 等会全部 404.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.core.asgi import get_asgi_application  # noqa: E402
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.auth import AuthMiddlewareStack  # noqa: E402

from apps.dashboard.routing import websocket_urlpatterns  # noqa: E402

# 用 ASGIStaticFilesHandler 包一层, 让 daphne 能服务 /static/ 下的 css/js.
# 即使 DEBUG=False 也保留这个 handler — 因为 ASGIStaticFilesHandler 内部
# 会先检查 STATIC_URL 前缀, 不匹配则 fallthrough 到 Django 应用本身.
django_asgi_app = ASGIStaticFilesHandler(get_asgi_application())

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
})

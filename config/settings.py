"""
Django settings for Strategic Radar Agent.

战略情报雷达 — 海外市场战略情报 Agent 项目主配置
"""
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent


# ----------------------------- .env 加载 -----------------------------
# 无依赖实现：项目根目录 .env 中以 KEY=VALUE 形式声明的变量在导入 settings
# 时被注入 os.environ；已存在的真实环境变量优先（避免覆盖容器/系统配置）。
def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        text = path.read_text(encoding='utf-8')
    except Exception:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            continue
        key, _, value = line.partition('=')
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(BASE_DIR / '.env')


SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'dev-strategic-radar-agent-secret-key-change-in-production',
)

# 生产环境必须显式设置 DJANGO_DEBUG=0
DEBUG = os.environ.get('DJANGO_DEBUG', '0') == '1'

# 生产环境必须显式设置 DJANGO_ALLOWED_HOSTS=example.com,api.example.com
# 默认仅允许本地访问；DEBUG=True 时自动放开常用本地域
_allowed_hosts_env = os.environ.get('DJANGO_ALLOWED_HOSTS', '').strip()
if _allowed_hosts_env:
    ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts_env.split(',') if h.strip()]
elif DEBUG:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0', '[::1]', 'testserver']
else:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1']

# ----------------------------- Apps -----------------------------
INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'corsheaders',
    'channels',

    'apps.sources',
    'apps.intelligence',
    'apps.analysis',
    'apps.briefings',
    'apps.notifications',
    'apps.dashboard',
    'apps.agents',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('PG_DB', 'strategic_radar'),
        'USER': os.environ.get('PG_USER', 'postgres'),
        'PASSWORD': os.environ.get('PG_PASSWORD', '123456'),
        'HOST': os.environ.get('PG_HOST', 'localhost'),
        'PORT': os.environ.get('PG_PORT', '5432'),
    }
}

REDIS_URL = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379')

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': f'{REDIS_URL}/1',
    }
}

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {'hosts': [(os.environ.get('REDIS_HOST', '127.0.0.1'),
                              int(os.environ.get('REDIS_PORT', 6379)))]},
    }
}

CELERY_BROKER_URL = f'{REDIS_URL}/2'
CELERY_RESULT_BACKEND = f'{REDIS_URL}/3'
CELERY_TIMEZONE = 'Asia/Shanghai'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
]

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CORS 白名单: 由 DJANGO_CORS_ORIGINS 环境变量控制 (逗号分隔)
# DEBUG=True 时为方便本地联调默认放开;
# 生产环境必须显式配置 DJANGO_CORS_ORIGINS, 空字符串等于完全禁用跨域
_cors_env = os.environ.get('DJANGO_CORS_ORIGINS', '').strip()
if _cors_env:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_env.split(',') if o.strip()]
    CORS_ALLOW_ALL_ORIGINS = False
elif DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
else:
    CORS_ALLOWED_ORIGINS = []
    CORS_ALLOW_ALL_ORIGINS = False

# 生产环境的安全头 (DEBUG=False 自动启用)
# 起动后可用 `python manage.py check --deploy` 验证, 必须 0 warning
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_REFERRER_POLICY = 'same-origin'
    SESSION_COOKIE_SECURE = os.environ.get('DJANGO_SESSION_COOKIE_SECURE', '1') == '1'
    CSRF_COOKIE_SECURE = os.environ.get('DJANGO_CSRF_COOKIE_SECURE', '1') == '1'
    # HSTS: 默认 1 年, 包含子域, 预加载名单 (首次上线可设为 60 调试)
    SECURE_HSTS_SECONDS = int(os.environ.get(
        'DJANGO_SECURE_HSTS_SECONDS', str(60 * 60 * 24 * 365)))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = os.environ.get(
        'DJANGO_HSTS_INCLUDE_SUBDOMAINS', '1') == '1'
    SECURE_HSTS_PRELOAD = os.environ.get('DJANGO_HSTS_PRELOAD', '1') == '1'
    # SSL 强制 (反向代理后端可以设 DJANGO_SSL_REDIRECT=0 交给上游)
    SECURE_SSL_REDIRECT = os.environ.get('DJANGO_SSL_REDIRECT', '1') == '1'
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
}

# ----------------------------- 业务配置 -----------------------------
LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'mock')
LLM_API_KEY = os.environ.get('LLM_API_KEY', '')
LLM_BASE_URL = os.environ.get('LLM_BASE_URL', '')
LLM_MODEL = os.environ.get('LLM_MODEL', 'mock-strategic-v1')

FEISHU_WEBHOOK_URL = os.environ.get('FEISHU_WEBHOOK_URL', '')
FEISHU_WEBHOOK_SECRET = os.environ.get('FEISHU_WEBHOOK_SECRET', '')

# 默认采用 SMTP 真发, 与 .env 保持一致;
# 演示/离线场景请显式设置 EMAIL_BACKEND=django.core.mail.backends.filebased.EmailBackend
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_FILE_PATH = os.environ.get(
    'EMAIL_FILE_PATH', str(BASE_DIR / 'tmp' / 'sent_emails'))
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.qq.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '465'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
# QQ 邮箱 587 + STARTTLS 在 AUTH 阶段易被服务端断开连接;
# 465 + SSL 为更稳定的交互方式. 默认按端口自动选择:
#   port == 465 → EMAIL_USE_SSL=True
#   port == 587 → EMAIL_USE_TLS=True
_email_use_tls_env = os.environ.get('EMAIL_USE_TLS')
_email_use_ssl_env = os.environ.get('EMAIL_USE_SSL')
_truthy = {'1', 'true', 'yes', 'on'}
if _email_use_ssl_env is not None or _email_use_tls_env is not None:
    EMAIL_USE_SSL = (str(_email_use_ssl_env or '').lower() in _truthy)
    EMAIL_USE_TLS = (str(_email_use_tls_env or '').lower() in _truthy)
    if EMAIL_USE_SSL and EMAIL_USE_TLS:
        # 互斥: 优先 SSL
        EMAIL_USE_TLS = False
else:
    EMAIL_USE_SSL = (EMAIL_PORT == 465)
    EMAIL_USE_TLS = (not EMAIL_USE_SSL)
DEFAULT_FROM_EMAIL = os.environ.get(
    'DEFAULT_FROM_EMAIL', EMAIL_HOST_USER or 'noreply@strategic-radar.local')

DEFAULT_NOTIFY_CHANNELS = ['feishu_webhook', 'email']

HIGH_IMPACT_THRESHOLD = 8

# ----------------------------- 降级与仿真切换 -----------------------------
# auto: 真实采集失败超过阈值后自动降级到仿真; simulated: 强制仿真; real: 仅真实采集
DATA_SOURCE_MODE = os.environ.get('DATA_SOURCE_MODE', 'auto')
# 同一信息源连续失败几次后被自动判定为不可用并切到仿真兜底
CRAWLER_FAILURE_THRESHOLD = int(os.environ.get('CRAWLER_FAILURE_THRESHOLD', '3'))
# 仿真兜底产出的最少情报条数 (保证简报不至空表)
MIN_SIMULATED_ITEMS = int(os.environ.get('MIN_SIMULATED_ITEMS', '1'))
# 真实采集失败时是否再用仿真兜底补一条 (auto 模式生效)
FALLBACK_ON_FAILURE = os.environ.get('FALLBACK_ON_FAILURE', '1') == '1'

# ----------------------------- 真实爬虫 API Key (可选) -----------------------------
# FRED API Key — 在 https://fred.stlouisfed.org/docs/api/api_key.html 免费申请
# 不设置时使用演示默认 key (可能被限流); 生产环境应在 .env 设置为专属 key
FRED_API_KEY = os.environ.get('FRED_API_KEY', '')

COMPANY_STRENGTHS = [
    '品牌全球认知度高',
    '供应链覆盖东亚 + 东南亚，弹性强',
    '研发投入持续高于行业均值',
]
COMPANY_WEAKNESSES = [
    '北美渠道议价能力较弱',
    '欧盟 ESG 合规体系尚未完全建立',
    '本地化营销团队薄弱',
]

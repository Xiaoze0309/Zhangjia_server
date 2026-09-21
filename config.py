import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'lanos-2.5-enhancement-secret-key')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'lanos.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

    # 站点域名配置
    SITE_MAIN = 'zhangjiacoins.dpdns.org'
    SITE_CENTER = 'zhangjiacenter.dpdns.org'
    SITE_INTRO = 'intro.zhangjiacoins.dpdns.org'
    SITE_TALK = 'talk.zhangjiacoins.dpdns.org'
    SITE_BETA = 'beta.zhangjiacoins.dpdns.org'

    # 评级价格
    RATING_PRICE = 50.00

    @staticmethod
    def init_app(app):
        pass

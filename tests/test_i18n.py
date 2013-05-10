# -*- coding: utf-8 -*-
from webtest import TestApp

import tg
from tg import i18n, expose, TGController, config
from tg.configuration import AppConfig
from tg.controllers.util import pylons_formencode_gettext

from tg._compat import unicode_text, u_

class TestSanitizeLanguage():
    def test_sanitize_language_code(self):
        """Check that slightly malformed language codes can be corrected."""
        for lang in 'pt', 'PT':
            assert i18n.sanitize_language_code(lang) == 'pt'
        for lang in 'pt-br', 'pt_br', 'pt_BR':
            assert i18n.sanitize_language_code(lang) == 'pt_BR'
        for lang in 'foo', 'bar', 'foo-bar':
            assert i18n.sanitize_language_code(lang) == lang

    def test_sanitize_language_code_charset(self):
        assert i18n.sanitize_language_code('en_US.UTF-8') == 'en_US'

    def test_sanitize_language_code_modifier(self):
        assert i18n.sanitize_language_code('it_IT@euro') == 'it_IT'

    def test_sanitize_language_code_charset_and_modifier(self):
        assert i18n.sanitize_language_code('de_DE.iso885915@euro') == 'de_DE'

    def test_sanitize_language_code_territory_script_variant(self):
        assert i18n.sanitize_language_code('zh_Hans_CN') == 'zh_CN'

    def test_sanitize_language_code_numeric(self):
        assert i18n.sanitize_language_code('es-419') == 'es_419'

    def test_sanitize_language_code_numeric_variant(self):
        assert i18n.sanitize_language_code('de-CH-1996') == 'de_CH'

def test_pylons_formencode_gettext_nulltranslation():
    prev_gettext = i18n.ugettext
    def nop_gettext(v):
        return v

    i18n.ugettext = nop_gettext
    assert pylons_formencode_gettext('something') == 'something'
    i18n.ugettext = prev_gettext
    return 'OK'

class i18nRootController(TGController):
    def _before(self, *args, **kw):
        if not tg.request.GET.get('skip_lang'):
            forced_lang = tg.request.GET.get('force_lang', 'de')
            i18n.set_temporary_lang(forced_lang)

        if tg.request.GET.get('fallback'):
            i18n.add_fallback(tg.request.GET.get('fallback'))

    @expose('json')
    def lazy_hello(self, **kw):
        return dict(text=unicode_text(i18n.lazy_ugettext('Your application is now running')))

    @expose('json')
    def get_lang(self, **kw):
        return dict(lang=i18n.get_lang())

    @expose('json')
    def hello(self, **kw):
        return dict(text=unicode_text(i18n.ugettext('Your application is now running')))

    @expose()
    def fallback(self, **kw):
        return i18n.ugettext('This is a fallback')

    @expose('json')
    def hello_plural(self):
        return dict(text=i18n.ungettext('Your application is now running',
                                        'Your applications are now running',
                                        2))

    @expose()
    def force_german(self, **kw):
        i18n.set_lang('de')
        return 'OK'

class TestI18NStack(object):
    def setup(self):
        class FakePackage:
            __name__ = 'tests'
            __file__ = __file__

            class lib:
                class app_globals:
                    class Globals:
                        pass
        FakePackage.__name__ = 'tests'

        conf = AppConfig(minimal=True, root_controller=i18nRootController())
        conf['paths']['root'] = 'tests'
        conf['i18n_enabled'] = True
        conf['use_sessions'] = True
        conf['beaker.session.key'] = 'tg_test_session'
        conf['beaker.session.secret'] = 'this-is-some-secret'
        conf.renderers = ['json']
        conf.default_renderer = 'json'
        conf.package = FakePackage()
        app = conf.make_wsgi_app()
        self.app = TestApp(app)

    def teardown(self):
        config.pop('tg.root_controller')

    def test_lazy_gettext(self):
        r = self.app.get('/lazy_hello')
        assert 'Ihre Anwendung' in r

    def test_plural_gettext(self):
        r = self.app.get('/hello_plural')
        assert 'Your applications' in r, r

    def test_get_lang(self):
        r = self.app.get('/get_lang?skip_lang=1')
        assert 'null' in r

    def test_gettext_default_lang(self):
        r = self.app.get('/hello?skip_lang=1')
        assert 'Your application' in r, r

    def test_gettext_nop(self):
        k = 'HELLO'
        assert i18n.gettext_noop(k) is k

    def test_null_translator(self):
        assert i18n._get_translator(None).gettext('Hello') == 'Hello'

    def test_get_lang_nonexisting_lang(self):
        r = self.app.get('/get_lang?force_lang=fa')
        assert 'null' in r, r

    def test_get_lang_existing(self):
        r = self.app.get('/get_lang?force_lang=de')
        assert 'de' in r, r

    def test_fallback(self):
        r = self.app.get('/fallback?force_lang=it&fallback=de')
        assert 'Dies ist' in r, r

    def test_force_lang(self):
        r = self.app.get('/get_lang?skip_lang=1')
        assert 'null' in r

        r = self.app.get('/force_german?skip_lang=1')
        assert 'tg_test_session' in r.headers.get('Set-cookie')

        cookie_value = r.headers.get('Set-cookie')
        r = self.app.get('/get_lang?skip_lang=1', headers={'Cookie':cookie_value})
        assert 'de' in r

    def test_get_lang_no_session(self):
        r = self.app.get('/get_lang?skip_lang=1', extra_environ={})
        assert 'null' in r

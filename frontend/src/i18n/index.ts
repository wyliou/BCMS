import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import zhTW from './zh-TW.json';

/**
 * Initializes i18next with zh-TW as the default and only language.
 * The init call is a module-level side effect — import this module
 * before rendering any component that uses useTranslation().
 */
i18n.use(initReactI18next).init({
  lng: 'zh-TW',
  fallbackLng: 'zh-TW',
  resources: {
    'zh-TW': { translation: zhTW },
  },
  interpolation: {
    escapeValue: false,
  },
  debug: false,
});

export default i18n;

import { createI18n } from 'vue-i18n'
import en from './locales/en.json'
import fr from './locales/fr.json'

function initialLocale() {
  try {
    const saved = localStorage.getItem('locale')
    if (saved === 'en' || saved === 'fr') return saved
  } catch { /* storage unavailable */ }
  return 'en'
}

const i18n = createI18n({
  legacy: false,
  locale: initialLocale(),
  fallbackLocale: 'en',
  messages: { en, fr },
})

/** Keep <html lang> in step with the UI language (screen readers, hyphenation). */
export function applyDocumentLang(code) {
  if (typeof document !== 'undefined' && document.documentElement) {
    document.documentElement.setAttribute('lang', code)
  }
}
applyDocumentLang(i18n.global.locale.value)

export default i18n

/**
 * Available locales for the language selector.
 */
export const LOCALES = [
  { code: 'en', label: 'EN', name: 'English', flag: '🇬🇧' },
  { code: 'fr', label: 'FR', name: 'Français', flag: '🇫🇷' },
]

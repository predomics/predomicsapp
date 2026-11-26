/** Display names for class labels: the user's own name when one was given, else "Class 0". */
import i18n from '../i18n'

/**
 * @param cls    raw class label (0, 1, "0", ...)
 * @param names  the project's class_names map, e.g. {"0": "Healthy", "1": "Cirrhosis"}
 */
export function classLabel(cls, names) {
  const custom = names && (names[String(cls)] ?? names[cls])
  if (custom !== undefined && custom !== null && String(custom).trim() && String(custom) !== String(cls)) {
    return String(custom)
  }
  return i18n.global.t('data.classN', { label: cls })
}

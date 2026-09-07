// Only the life simulator uses this device restriction.
export function isLifeDesktop() {
  return window.matchMedia('(min-width: 901px)').matches &&
    !/Android|iPhone|iPod|Windows Phone|IEMobile/i.test(navigator.userAgent)
}

/**
 * Google Consent Mode v2 defaults, everything denied (owner decisions 28 and
 * 32), set before any Google script could run. Advertising storage, ad user
 * data and ad personalisation stay denied for good; analytics storage changes
 * only through the consent store, once the API has recorded a yes. Plain ES5:
 * it runs inline and is not transpiled. It loads nothing and sends nothing.
 */
export const CONSENT_MODE_DEFAULTS = [
  'window.dataLayer=window.dataLayer||[];',
  'window.gtag=window.gtag||function(){window.dataLayer.push(arguments)};',
  "window.gtag('consent','default',{",
  "ad_storage:'denied',ad_user_data:'denied',ad_personalization:'denied',",
  "analytics_storage:'denied',functionality_storage:'denied',personalization_storage:'denied',",
  "security_storage:'granted',wait_for_update:500});",
  "window.gtag('set','ads_data_redaction',true);",
].join('');

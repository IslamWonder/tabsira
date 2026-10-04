// The admin script. sqladmin's own script does three things the admin area must not leave
// as they are: it deletes with a request that carries no CSRF token, it runs bulk actions by
// navigating to a GET address, and it links an action on a record page the same way. This
// file, loaded after sqladmin's, fixes all three. Forms need nothing here: the server puts
// the token in each of them.
(() => {
  const meta = document.querySelector('meta[name="csrf-token"]');
  const token = meta ? meta.content : '';

  // Requests made with jQuery (the delete confirmation) carry the token in a header.
  if (window.jQuery && token) {
    window.jQuery.ajaxSetup({ headers: { 'X-CSRF-Token': token } });
  }

  // The primary keys of the rows ticked in a list: each row holds its key in a hidden input
  // beside the checkbox.
  function selectedKeys() {
    return Array.from(document.querySelectorAll('.select-box:checked'))
      .map((box) => Array.from(box.parentElement.children).find((element) => element !== box))
      .filter((input) => input?.value)
      .map((input) => input.value);
  }

  // Run an action as a POST with the token in the body.
  function post(url) {
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = url;
    const field = document.createElement('input');
    field.type = 'hidden';
    field.name = 'csrf_token';
    field.value = token;
    form.append(field);
    document.body.append(form);
    form.submit();
  }

  // Captured on the document, so it runs before sqladmin's own handlers on the links.
  document.addEventListener(
    'click',
    (event) => {
      const link = event.target instanceof Element ? event.target.closest('a') : null;
      if (!link) {
        return;
      }
      let url = null;
      if (link.id.startsWith('action-custom-') && link.dataset.url) {
        url = `${link.dataset.url}?pks=${selectedKeys().join(',')}`;
      } else if ((link.getAttribute('href') || '').includes('/action/')) {
        url = link.href;
      }
      if (url !== null) {
        event.preventDefault();
        event.stopImmediatePropagation();
        post(url);
      }
    },
    true
  );
})();

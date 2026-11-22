// Tell the server the browser's time zone, so times are typed and shown in local time.
// Also keep date pickers marked data-min-today from offering days before today.
(function () {
  var zone = "";
  try { zone = Intl.DateTimeFormat().resolvedOptions().timeZone || ""; } catch (e) { zone = ""; }
  if (/^[A-Za-z0-9_+\-\/]{1,64}$/.test(zone) && document.cookie.split("; ").indexOf("pv_tz=" + zone) === -1) {
    document.cookie = "pv_tz=" + zone + "; path=/; max-age=31536000; samesite=lax";
  }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function today() {
    var d = new Date();
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
  }
  function limit(root) {
    var inputs = (root || document).querySelectorAll("input[type=date][data-min-today]");
    for (var i = 0; i < inputs.length; i++) {
      var input = inputs[i], first = today();
      if (input.value && input.value < first) { first = input.value; }  // keep a saved earlier day
      input.min = first;
    }
  }
  document.addEventListener("DOMContentLoaded", function () { limit(document); });
  document.addEventListener("htmx:afterSwap", function (e) { limit(e.target); });
})();

/**
 * 303 redirect with a relative Location header.
 *
 * NextResponse.redirect() needs an absolute URL, and `new URL(path, req.url)`
 * resolves against `req.url` — which inside a container with HOSTNAME=0.0.0.0
 * comes back as `http://0.0.0.0:3000/...`. The browser then follows the
 * Location to `0.0.0.0` and the navigation fails because that address
 * isn't routable client-side. Symptom: user submits a form, page hangs
 * or shows nothing, and a manual refresh "fixes" it because the cookie
 * was already set during the failed redirect.
 *
 * Browsers resolve relative Locations against the URL they actually
 * requested, so a relative redirect always lands the user back on
 * whatever host they were already on (localhost, 127.0.0.1, or a real
 * domain in production).
 */
export function relativeRedirect(path: string): Response {
  return new Response(null, {
    status: 303,
    headers: { Location: path },
  });
}

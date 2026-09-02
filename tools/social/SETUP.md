# Instagram publishing setup (Graph API)

**Status (2026-09-02): configured.** Meta app "Practical Rewards Publisher"
(app id 1725463365384371, Instagram app id 1582616906672673) owned by Carter's
Facebook developer account; practical.rewards is a Business account and an
Instagram Tester on the app; config lives at
`~/.config/practicalrewards/instagram.json` (Instagram-Login flavor,
graph.instagram.com). The publisher refreshes the 60-day token automatically
once a week. `python3 tools/instagram_publish.py --check` verifies it.

If the token ever dies: open the OAuth URL in the practicalrewards Chrome
profile (`https://www.instagram.com/oauth/authorize?client_id=1582616906672673&redirect_uri=https%3A%2F%2Fpracticalrewards.com%2F&response_type=code&scope=instagram_business_basic%2Cinstagram_business_content_publish`),
click Allow, take the `code` from the redirect URL, and exchange it with the app
secret (dashboard → Instagram app secret → copy) at
`POST https://api.instagram.com/oauth/access_token`, then
`GET https://graph.instagram.com/access_token?grant_type=ig_exchange_token`.
The dashboard's own "Generate token" button opens a popup Chrome blocks.


The daily pipeline generates `social/<slug>/` (slides, `og.png`, `caption.md`,
`post.json`) for every post. Publishing to Instagram happens once, at
`tools/publish.sh` time, through the Instagram Graph API. It needs a one-time
setup that only the account owner can do.

## One-time setup (Instagram Login flavor, no Facebook Page needed)

1. Instagram: Settings → Account type and tools → Switch to professional account.
2. https://developers.facebook.com (needs a Facebook login) → Create app → use
   case "Instagram" (API with Instagram Login) → in the app dashboard open
   Instagram → API setup with Instagram login → step 1 "Generate access tokens":
   add the practical.rewards account and generate a token (it is long-lived,
   60 days; refresh with GET /refresh_access_token?grant_type=ig_refresh_token).
3. The dashboard shows the Instagram account id next to the token.
4. Save `{"ig_user_id": "...", "access_token": "IGAA...", "graph_host": "https://graph.instagram.com"}`
   at `~/.config/practicalrewards/instagram.json` (chmod 600) and run
   `python3 tools/instagram_publish.py --check`.

## Alternative setup (Facebook Login flavor)

1. **Instagram account type.** In the Instagram app: Settings → Account type
   and tools → Switch to professional account → Creator (or Business).
2. **Facebook Page.** Create (or pick) a Facebook Page and link it to the
   Instagram account: Instagram → Settings → Accounts Center → Add accounts.
3. **Meta app.** At https://developers.facebook.com create an app (type
   Business), add the *Instagram Graph API* product. No app review is
   needed while the token belongs to the app admin.
4. **Token.** In Graph API Explorer pick the app, add permissions
   `instagram_basic`, `instagram_content_publish`, `pages_show_list`,
   `pages_read_engagement`, then Generate Access Token. Exchange it for a
   long-lived token (60 days), then fetch a Page token from
   `/me/accounts` — Page tokens made from a long-lived user token do not
   expire.
5. **Instagram user id.** `GET /<page-id>?fields=instagram_business_account`
   returns the id to use.
6. Save the config outside the repo:

   ```json
   {"ig_user_id": "1784...", "access_token": "EAAB...", "api_version": "v21.0"}
   ```

   at `~/.config/practicalrewards/instagram.json` (chmod 600).
7. Verify: `python3 tools/instagram_publish.py --check` prints the account.

## Daily flow

- `run_daily.py` runs the `social` step after verification. Failure there
  never blocks the post; the share-image tags are stripped instead.
- `publish.sh` pushes main, then calls `instagram_publish.py --latest`, which
  waits for Render to serve the slide URLs and posts them.
- Publish records live in `tools/state/instagram.json` (git-ignored); a slug
  is never posted twice.
- Regenerate a post's assets: `python3 tools/social.py <slug> --force`.
- Manual publish or retry: `python3 tools/instagram_publish.py --slug <slug>`.

## Limits worth knowing

- Instagram accepts JPEG only for image posts; slides are exported as JPEG.
- 25 API-published posts per 24 hours per account (we use 1).
- Carousels: 2–10 items; the pipeline produces 3–5.

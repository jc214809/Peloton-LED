# Peloton's unofficial API

Peloton publishes no API. Everything here comes from community reverse engineering, and Peloton can change or remove any of it without notice.

Each endpoint below has a **Source** line saying how much to trust it:

- **Board**: this project calls it every day, so it is known to work (as of November 2026). The sample response shows the fields the board reads, plus a few common ones that the note under it names when they matter.
- **Tested**: called once by hand (the date is given), and the sample follows the real response with the values replaced.
- **Spec**: from the community OpenAPI spec and Postman collections, untested here. The sample response follows the spec's schema.
- **Undocumented**: the sources name the endpoint but don't describe its response.

Every ID, name and number in the examples is made up, so the examples are safe to share. Sample responses are trimmed to the useful fields, and real ones have many more.

## Contents

- [Hosts](#hosts)
- [Authentication](#authentication) and [headers](#headers)
- [Setup for the examples](#setup-for-the-examples)
- [Auth (legacy)](#auth-legacy)
- [You and other members](#you-and-other-members)
- [Workouts](#workouts)
- [Classes (rides)](#classes-rides)
- [Instructors](#instructors)
- [Challenges](#challenges)
- [GraphQL (tags)](#graphql-tags)
- [Gotchas](#gotchas)
- [Sources](#sources)

## Hosts

| Host | What it is |
|---|---|
| `https://api.onepeloton.com` | The main REST API. Every path below is on this host unless it says otherwise. |
| `https://auth.onepeloton.com` | Auth0 login and token renewal. |
| `https://gql-graphql-gateway.prod.k8s.onepeloton.com/graphql` | The GraphQL gateway (tags). |
| `https://members.onepeloton.com/login` | The web login page that issues the tokens. |

## Authentication

There are two schemes. Use the first; the second is how the older docs and clients worked.

### Bearer token (current)

Peloton's web app logs in through Auth0 (client ID `WVoJxVDdPoFx4RNewvvg6ch2mZ7bwnsM`, scope includes `offline_access`). After a browser login, the page's localStorage holds an `@@auth0spajs@@::…` entry whose `body` has an `access_token` and a `refresh_token`. `scripts/refresh_cookies.py` does this login with Playwright.

- **Calling the API:** send `Authorization: Bearer <access_token>`. An access token lasts about 48 hours.
- **Refresh tokens work once.** Reusing an old one gets `403 invalid_grant`. Save the new one before doing anything else, and never share a refresh token between two machines.

**Renew an access token** (Source: Board)

```bash
curl -sS -X POST https://auth.onepeloton.com/oauth/token \
  -H "Content-Type: application/json" \
  -d '{"grant_type": "refresh_token",
       "client_id": "WVoJxVDdPoFx4RNewvvg6ch2mZ7bwnsM",
       "refresh_token": "v1.MExampleRefreshToken"}'
```

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.example.signature",
  "refresh_token": "v1.MNewExampleRefreshToken",
  "scope": "openid profile email offline_access",
  "expires_in": 172800,
  "token_type": "Bearer"
}
```

A refresh token that has already been used gets `403` with `{"error": "invalid_grant", "error_description": "Unknown or invalid refresh token."}`.

### Session cookie (legacy)

`POST /auth/login` with `username_or_email` and `password` returned a `session_id`. Later calls sent it as the cookie `peloton_session_id`. Peloton no longer issues these sessions to scripts (the comment in `scripts/refresh_cookies.py` and at least one client project say so). Treat the `/auth/*` endpoints below as historical.

### Headers

| Header | When |
|---|---|
| `Authorization: Bearer <token>` | Every endpoint marked **Token**. |
| `peloton-platform: web` | Every endpoint marked **Platform**. Without it, newer endpoints return less data or none. `overview` leaves out personal records, for example. It is harmless to send on every request, which is what the board does. |
| `Content-Type: application/json` | Every POST or PUT with a body. |
| `User-Agent` | Anything works. The board sends `peloton-led/1.0`. |

What the **Auth** line on each endpoint means:

- **None**: the older docs list this as anonymous. Peloton locked down member data after a 2021 security report, so expect some of these to need a token now.
- **Token**: needs the bearer token (or the legacy cookie).
- **Token + Platform**: also needs `peloton-platform: web`.

## Setup for the examples

The curl examples use a small shell helper so each one stays short. The helper sends the token, the platform header and the JSON content type on every call, which is what the board does too.

```bash
export PELOTON_TOKEN='eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.example.signature'
export PELOTON_USER='0123456789abcdef0123456789abcdef'   # your "id" from /api/me
API=https://api.onepeloton.com

pt() {
  curl -sS -H "Authorization: Bearer $PELOTON_TOKEN" \
       -H "peloton-platform: web" \
       -H "Content-Type: application/json" "$@"
}

pt "$API/api/me" | jq .          # jq is optional; it pretty-prints
```

The same thing in Python:

```python
import requests

session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {token}",
    "peloton-platform": "web",
    "User-Agent": "my-peloton-script/1.0",
})
me = session.get("https://api.onepeloton.com/api/me", timeout=15).json()
workouts = session.get(
    f"https://api.onepeloton.com/api/user/{me['id']}/workouts",
    params={"joins": "ride,ride.instructor", "limit": 20, "page": 0},
    timeout=20,
).json()
```

Example IDs used below:

| Name | Example value |
|---|---|
| User ID | `0123456789abcdef0123456789abcdef` |
| Workout ID | `aaaa1111bbbb2222cccc3333dddd4444` |
| Ride (class) ID | `bbbb2222cccc3333dddd4444eeee5555` |
| Instructor ID | `cccc3333dddd4444eeee5555ffff6666` |
| Challenge ID | `dddd4444eeee5555ffff6666aaaa7777` |
| Scheduled class (peloton) ID | `eeee5555ffff6666aaaa7777bbbb8888` |

Times are Unix seconds unless they say otherwise.

---

## Auth (legacy)

### `POST /auth/login`

Logs in with a username or email and a password, and returns a session. Peloton no longer issues these sessions to scripts; use the bearer token instead.

**Auth:** None · **Source:** Spec

```bash
curl -sS -X POST "$API/auth/login" -H "Content-Type: application/json" \
  -d '{"username_or_email": "rider@example.com", "password": "example-password", "with_pubsub": false}'
```

```json
{
  "session_id": "exampleSessionId123",
  "user_id": "0123456789abcdef0123456789abcdef",
  "user_data": {
    "id": "0123456789abcdef0123456789abcdef",
    "username": "RiderOne",
    "total_workouts": 412,
    "is_profile_private": false
  }
}
```

### `POST /auth/logout`

Ends a session.

**Auth:** Token · **Source:** Undocumented

```bash
pt -X POST "$API/auth/logout" -d '{"session_id": "exampleSessionId123"}'
```

### `GET /auth/check_session`

Says whether the session is still valid and returns the profile.

**Auth:** Token · **Source:** Spec (the response is an object with the session and the profile)

```bash
pt "$API/auth/check_session"
```

---

## You and other members

### `GET /api/me`

Your own account. Start here to get your user ID (`id`).

**Auth:** Token + Platform · **Source:** Board · **Params:** `is_onboarded` (optional)

```bash
pt "$API/api/me"
```

```json
{
  "id": "0123456789abcdef0123456789abcdef",
  "username": "RiderOne",
  "image_url": "https://example.com/profile.png",
  "location": "Columbus, OH",
  "total_workouts": 412,
  "total_followers": 38,
  "total_following": 41,
  "created_at": 1577836800,
  "last_workout_at": 1763042400,
  "is_profile_private": false,
  "workout_counts": [
    {"name": "Cycling", "slug": "cycling", "count": 251},
    {"name": "Strength", "slug": "strength", "count": 97},
    {"name": "Tread Bootcamp", "slug": "bootcamp", "count": 12}
  ],
  "cycling_ftp": 210,
  "default_max_heart_rate": 178
}
```

### `GET /api/user/{user_id or username}`

Any member's public profile. Your own token returns more fields.

**Auth:** None (more with Token) · **Source:** Spec · **Params:** `is_onboarded` (optional)

```bash
pt "$API/api/user/RiderTwo"
```

```json
{
  "id": "1123456789abcdef0123456789abcdef",
  "username": "RiderTwo",
  "image_url": "https://example.com/profile2.png",
  "location": "Columbus, OH",
  "is_profile_private": false,
  "total_workouts": 389,
  "total_followers": 52,
  "total_following": 47,
  "authed_user_follows": true,
  "relationship": {"me_to_user": "following", "user_to_me": "following"}
}
```

### `PUT /api/user/{user_id}`

Updates your profile.

**Auth:** Token · **Source:** Undocumented (Postman collection only) · **Body:** the profile fields to change

```bash
pt -X PUT "$API/api/user/$PELOTON_USER" -d '{"location": "Columbus, OH"}'
```

### `GET /api/user/{user_id}/overview`

Your personal records per discipline, workout counts, streaks and achievement totals. Without the platform header, `personal_records` is missing.

**Auth:** Token + Platform · **Source:** Board · **Params:** `version=1`

```bash
pt "$API/api/user/$PELOTON_USER/overview?version=1"
```

```json
{
  "id": "0123456789abcdef0123456789abcdef",
  "workout_counts": {
    "total_workouts": 412,
    "workouts": [
      {"name": "Cycling", "slug": "cycling", "count": 251},
      {"name": "Strength", "slug": "strength", "count": 97}
    ]
  },
  "personal_records": [
    {
      "name": "Cycling",
      "slug": "cycling",
      "records": [
        {"name": "20 min", "slug": "20_min", "value": 245, "raw_value": 245.1,
         "unit": "kj", "unit_slug": "kj",
         "workout_id": "aaaa1111bbbb2222cccc3333dddd4444", "workout_date": "2026-10-04T12:00:00"},
        {"name": "30 min", "slug": "30_min", "value": 352, "raw_value": 351.8,
         "unit": "kj", "unit_slug": "kj",
         "workout_id": "aaaa1111bbbb2222cccc3333dddd5555", "workout_date": "2026-09-12T12:00:00"}
      ]
    }
  ],
  "streaks": {
    "current_weekly": 14,
    "best_weekly": 52,
    "current_daily": 3,
    "start_date_of_current_daily": 1762819200
  },
  "achievements": [
    {"id": "f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0", "name": "Best Output", "slug": "best_output",
     "image_url": "https://example.com/badge.png", "description": "Personal best output in a workout."}
  ]
}
```

### `GET /api/user/{user_id}/calendar`

The days you worked out, grouped by month.

**Auth:** Token · **Source:** Undocumented (the spec calls it "active days by month" but gives no shape)

```bash
pt "$API/api/user/$PELOTON_USER/calendar"
```

### `GET /api/user/{user_id}/settings`

Your account settings: units, privacy, captions and connected services.

**Auth:** Token + Platform · **Source:** Spec

```bash
pt "$API/api/user/$PELOTON_USER/settings"
```

```json
{
  "distance_unit": "imperial",
  "weight_unit": "lb",
  "height_unit": "in",
  "block_explicit": false,
  "auto_post_workout_to_strava": false,
  "auto_post_workout_to_fitbit": false,
  "privacy": {
    "is_profile_private": false,
    "age": false,
    "weight": false,
    "workout_maps_private": true
  },
  "closed_captions": {"enabled": false}
}
```

### `PUT /api/user/{user_id}/settings`

Changes your settings.

**Auth:** Token · **Source:** Undocumented (Postman collection only) · **Body:** the settings to change

```bash
pt -X PUT "$API/api/user/$PELOTON_USER/settings" -d '{"block_explicit": true}'
```

### `GET /api/user/{user_id}/achievements`

Every badge, with how many times you've earned each.

**Auth:** Token + Platform · **Source:** Spec (the badges follow its `AchievementTemplate` schema; the grouping around them is not described)

```bash
pt "$API/api/user/$PELOTON_USER/achievements"
```

Each badge looks like this:

```json
{
  "id": "f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0",
  "name": "Best Output",
  "slug": "best_output",
  "image_url": "https://example.com/badge.png",
  "description": "Personal best output in a workout."
}
```

### `GET /api/user/{user_id}/followers`

People who follow you.

**Auth:** Token · **Source:** Spec · **Params:** `page`, `limit`

```bash
pt "$API/api/user/$PELOTON_USER/followers?limit=20&page=0"
```

```json
{
  "data": [
    {"id": "1123456789abcdef0123456789abcdef", "username": "RiderTwo",
     "location": "Columbus, OH", "total_workouts": 389, "authed_user_follows": true,
     "relationship": {"me_to_user": "following", "user_to_me": "following"}}
  ],
  "limit": 20, "page": 0, "total": 38, "count": 20, "page_count": 2,
  "show_previous": false, "show_next": true
}
```

### `GET /api/user/{user_id}/following`

People you follow. The response looks like `followers`.

**Auth:** Token · **Source:** Spec · **Params:** `joins`, `page`, `limit`

```bash
pt "$API/api/user/$PELOTON_USER/following?limit=20&page=0"
```

### `GET /api/user/{user_id}/facebook_friends`

Facebook friends who are also members.

**Auth:** Token + Platform · **Source:** Spec (a list of profiles, like `followers`)

```bash
pt "$API/api/user/$PELOTON_USER/facebook_friends"
```

### `GET /api/user/search`

Finds members by name. The response is a list of profiles, like `followers`.

**Auth:** Token + Platform · **Source:** Spec · **Params:** `user_query`, `limit` (default 40)

```bash
pt "$API/api/user/search?user_query=RiderTwo&limit=40"
```

### `POST /api/user/change_relationship`

Follows or unfollows a member.

**Auth:** Token + Platform · **Source:** Spec · **Body:** `action` (`follow` or `unfollow`), `user_id`

```bash
pt -X POST "$API/api/user/change_relationship" \
  -d '{"action": "follow", "user_id": "1123456789abcdef0123456789abcdef"}'
```

```json
{"me_to_user": "following", "user_to_me": "none"}
```

`me_to_user` is `follow_pending` when the other profile is private.

### `GET /api/user/{user_id}/image_upload_url`

Gets a URL for a new profile photo. PUT the image to `upload_url`; it then shows at `new_image_url`.

**Auth:** Token · **Source:** Spec

```bash
pt "$API/api/user/$PELOTON_USER/image_upload_url"
```

```json
{
  "upload_url": "https://example-bucket.s3.amazonaws.com/upload?signature=example",
  "new_image_url": "https://example.com/new-profile.png"
}
```

### `GET /api/user/{user_id}/referral_history`

Your referrals and your referral coupon code.

**Auth:** Token + Platform · **Source:** Undocumented

```bash
pt "$API/api/user/$PELOTON_USER/referral_history"
```

### `GET /api/v2/user/subscriptions`

Your memberships: type, status and renewal date.

**Auth:** Token + Platform · **Source:** Undocumented

```bash
pt "$API/api/v2/user/subscriptions"
```

### `GET /api/user/{user_id}/subscription/{subscription_id}/subscription_transactions`

Billing history for one membership. Get the subscription ID from `/api/v2/user/subscriptions`.

**Auth:** Token · **Source:** Undocumented · **Params:** `joins=transaction`, `limit=12`

```bash
pt "$API/api/user/$PELOTON_USER/subscription/SUBSCRIPTION_ID/subscription_transactions?joins=transaction&limit=12"
```

---

## Workouts

A *workout* is one time you did a class (or a Just Ride or Just Run). A *ride* is the class itself, which is shared by everyone who took it.

### `GET /api/user/{user_id}/workouts`

Your workout history, newest first, one page at a time.

**Auth:** Token · **Source:** Board

**Params:**

- `limit` and `page` (from 0)
- `sort_by=-created`
- `joins=ride,ride.instructor`, which adds the class and instructor to each row
- `ride_id`, which returns only that class
- `from` and `to`, an ISO 8601 UTC date range

```bash
pt "$API/api/user/$PELOTON_USER/workouts?joins=ride,ride.instructor&limit=20&page=0&sort_by=-created"

# Everything in October 2026
pt "$API/api/user/$PELOTON_USER/workouts?from=2026-10-01T00:00:00Z&to=2026-11-01T00:00:00Z&joins=ride"
```

```json
{
  "data": [
    {
      "id": "aaaa1111bbbb2222cccc3333dddd4444",
      "created_at": 1763042400,
      "start_time": 1763042402,
      "end_time": 1763044202,
      "status": "COMPLETE",
      "fitness_discipline": "cycling",
      "metrics_type": "cycling",
      "workout_type": "class",
      "device_type": "home_bike_v1",
      "total_work": 352214.5,
      "is_total_work_personal_record": true,
      "has_leaderboard_metrics": true,
      "timezone": "America/New_York",
      "ride": {
        "id": "bbbb2222cccc3333dddd4444eeee5555",
        "title": "30 min Pop Ride",
        "duration": 1800,
        "fitness_discipline": "cycling",
        "instructor": {"id": "cccc3333dddd4444eeee5555ffff6666", "name": "Coach Example"}
      }
    }
  ],
  "limit": 20, "page": 0, "total": 412, "count": 20, "page_count": 21,
  "show_previous": false, "show_next": true, "sort_by": "-created_at,-pk"
}
```

`total_work` is in joules, so this ride was 352 kJ. Keep paging until `show_next` is `false`.

### `GET /api/user/{user_id}/workout_history_csv`

Your whole history as a CSV, the same file as the website's download button.

**Auth:** Token · **Source:** Undocumented (Postman collection only) · **Params:** `timezone`

```bash
pt "$API/api/user/$PELOTON_USER/workout_history_csv?timezone=America/New_York" -o workouts.csv
```

### `GET /api/workout/{workout_id}`

One workout in full. It has the fields of a list row plus leaderboard rank and the number of riders on the leaderboard. A strength class with the movement tracker also has `movement_tracker_data`.

**Auth:** Token · **Source:** Board · **Params:** `joins=ride,ride.instructor`

```bash
pt "$API/api/workout/aaaa1111bbbb2222cccc3333dddd4444?joins=ride,ride.instructor"
```

```json
{
  "id": "aaaa1111bbbb2222cccc3333dddd4444",
  "status": "COMPLETE",
  "fitness_discipline": "strength",
  "start_time": 1763042402,
  "end_time": 1763044202,
  "leaderboard_rank": 1204,
  "total_leaderboard_users": 9876,
  "ride": {"id": "bbbb2222cccc3333dddd4444eeee5555", "title": "30 min Full Body Strength"},
  "movement_tracker_tier": "gold",
  "movement_tracker_data": {
    "completed_movements_summary_data": {
      "total_repetitions": 214,
      "total_volume": 4280,
      "weight_unit": "lb",
      "num_movements": 9,
      "num_targets_reached": 7,
      "completion_percentage": 88,
      "longest_streak": 5,
      "repetition_summary_data": [
        {"movement_id": "m1", "movement_name": "Bent Over Row", "tracking_type": "rep_based",
         "offset": 300, "length": 45, "completed_number": 12, "target_number": 12,
         "is_target_reached": true, "is_hold": false, "total_volume": 360,
         "weight": [{"weight_category": "medium", "weight_data": {"weight_value": 30}}]}
      ],
      "movement_aggregate_data": [
        {"movement_name": "Bent Over Row", "tags": ["most_volume"],
         "stats": [{"slug": "total_reps", "completed_number": 36},
                   {"slug": "total_volume", "completed_number": 1080}]}
      ],
      "weight_info_summary_data": {
        "medium_weights": [{"weight_value": 30, "weight_unit": "lb"}]
      }
    }
  }
}
```

### `GET /api/workout/{workout_id}/performance_graph`

The second-by-second metrics of a workout: output, cadence, resistance, speed and heart rate, sampled every `every_n` seconds. It also has the totals, averages, maximums, heart-rate zones, Strive Score, the class's segments and the instructor's target ranges.

**Auth:** Token · **Source:** Board · **Params:** `every_n` (1 = every second; the board uses 5)

```bash
pt "$API/api/workout/aaaa1111bbbb2222cccc3333dddd4444/performance_graph?every_n=5"
```

```json
{
  "duration": 1800,
  "seconds_since_pedaling_start": [0, 5, 10, 15],
  "summaries": [
    {"display_name": "Total Output", "slug": "total_output", "value": 352, "display_unit": "kj"},
    {"display_name": "Distance", "slug": "distance", "value": 10.4, "display_unit": "mi"},
    {"display_name": "Calories", "slug": "calories", "value": 410, "display_unit": "kcal"}
  ],
  "metrics": [
    {"display_name": "Output", "slug": "output", "display_unit": "watts",
     "values": [120, 165, 190, 210], "average_value": 196, "max_value": 402},
    {"display_name": "Cadence", "slug": "cadence", "display_unit": "rpm",
     "values": [78, 84, 88, 90], "average_value": 86, "max_value": 112},
    {"display_name": "Resistance", "slug": "resistance", "display_unit": "%",
     "values": [35, 40, 42, 45], "average_value": 42, "max_value": 60},
    {"display_name": "Heart Rate", "slug": "heart_rate", "display_unit": "bpm",
     "values": [102, 118, 131, 140], "average_value": 142, "max_value": 171,
     "zones": [
       {"display_name": "Zone 1", "slug": "zone1", "duration": 120},
       {"display_name": "Zone 2", "slug": "zone2", "duration": 540},
       {"display_name": "Zone 3", "slug": "zone3", "duration": 780},
       {"display_name": "Zone 4", "slug": "zone4", "duration": 300},
       {"display_name": "Zone 5", "slug": "zone5", "duration": 60}
     ]}
  ],
  "effort_zones": {
    "total_effort_points": 48.2,
    "heart_rate_zone_durations": {
      "heart_rate_z1_duration": 120, "heart_rate_z2_duration": 540,
      "heart_rate_z3_duration": 780, "heart_rate_z4_duration": 300,
      "heart_rate_z5_duration": 60
    }
  },
  "segment_list": [
    {"name": "Warm Up", "icon_slug": "warmup", "start_time_offset": 0, "length": 300},
    {"name": "Cycling", "icon_slug": "cycling", "start_time_offset": 300, "length": 1320},
    {"name": "Cool Down", "icon_slug": "cooldown", "start_time_offset": 1620, "length": 180}
  ],
  "target_performance_metrics": {
    "target_graph_metrics": [
      {"type": "cadence", "graph_data": {"lower": [80, 80, 90, 90], "upper": [90, 90, 100, 100]}},
      {"type": "resistance", "graph_data": {"lower": [30, 30, 40, 40], "upper": [40, 40, 50, 50]}}
    ]
  }
}
```

Equipment decides which metrics are present. A strength class has heart rate only, and a treadmill has speed and incline in place of cadence and resistance (see `docs/DATA-POINTS.md`).

### `DELETE /api/workout/{workout_id}`

Deletes a workout from your history. **This cannot be undone.**

**Auth:** Token · **Source:** Undocumented (Postman collection only)

```bash
pt -X DELETE "$API/api/workout/aaaa1111bbbb2222cccc3333dddd4444"
```

---

## Classes (rides)

### `GET /api/ride/{ride_id}`

One class: title, instructor, length, difficulty and air date.

**Auth:** Token · **Source:** Spec (the same `ride` object that `details` returns below)

```bash
pt "$API/api/ride/bbbb2222cccc3333dddd4444eeee5555"
```

### `GET /api/ride/{ride_id}/details`

The class plus its segments (warm-up, intervals and cool-down), target metrics and playlist.

**Auth:** Token + Platform · **Source:** Board · **Params:** `stream_source=multichannel` (optional; adds stream info)

```bash
pt "$API/api/ride/bbbb2222cccc3333dddd4444eeee5555/details"
```

```json
{
  "ride": {
    "id": "bbbb2222cccc3333dddd4444eeee5555",
    "title": "30 min Pop Ride",
    "description": "An upbeat ride to your favorite pop hits.",
    "fitness_discipline": "cycling",
    "fitness_discipline_display_name": "Cycling",
    "duration": 1800,
    "length": 1890,
    "instructor_id": "cccc3333dddd4444eeee5555ffff6666",
    "original_air_time": 1761998400,
    "difficulty_rating_avg": 7.8,
    "overall_rating_avg": 0.99,
    "total_workouts": 15234,
    "has_pedaling_metrics": true,
    "is_explicit": false,
    "image_url": "https://example.com/class.jpg"
  },
  "segments": {
    "segment_list": [
      {"name": "Warm Up", "icon_slug": "warmup", "start_time_offset": 0, "length": 300},
      {"name": "Cycling", "icon_slug": "cycling", "start_time_offset": 300, "length": 1320},
      {"name": "Cool Down", "icon_slug": "cooldown", "start_time_offset": 1620, "length": 180}
    ]
  },
  "target_metrics_data": {
    "target_metrics": [
      {"offsets": {"start": 300, "end": 360},
       "metrics": [{"name": "cadence", "lower": 80, "upper": 90},
                   {"name": "resistance", "lower": 30, "upper": 40}]}
    ]
  },
  "playlist": {
    "songs": [{"title": "Example Song", "artists": [{"artist_name": "Example Artist"}]}]
  }
}
```

The board uses the `ride` object and the segments. The `target_metrics_data` and `playlist` shapes come from community clients and haven't been checked here.

### `GET /api/ride/{ride_id}/recent_following_workouts`

Recent workouts of this class by people you follow.

**Auth:** Token + Platform · **Source:** Undocumented · **Params:** `joins=user`, `limit`, `page`, `sort_by`

```bash
pt "$API/api/ride/bbbb2222cccc3333dddd4444eeee5555/recent_following_workouts?joins=user&limit=50"
```

### `GET /api/ride/metadata_mappings`

Lookup tables for class types, disciplines, equipment and difficulty levels. Use them to turn IDs like `ride_type_id` into names.

**Auth:** Token + Platform (listed as None in older docs) · **Source:** Undocumented

```bash
pt "$API/api/ride/metadata_mappings"
```

### `GET /api/ride/filters`

The filter options the class library shows: durations, class types, instructors, music and bookmarks.

**Auth:** Token + Platform · **Source:** Spec · **Params:** `library_type`, `browse_category`, `include_icon_images`

```bash
pt "$API/api/ride/filters?library_type=on_demand&browse_category=cycling&include_icon_images=true"
```

One filter looks like this:

```json
{
  "name": "is_favorite_ride",
  "display_name": "Bookmarked",
  "type": "toggle",
  "user_specific": true,
  "values": [{"value": "true", "display_name": "Bookmarked"}]
}
```

### `GET /api/v2/ride/archived`

The on-demand class library, searchable and paged.

**Auth:** Token + Platform · **Source:** Spec

**Params:**

- `browse_category`: `cycling`, `running`, `strength`, `yoga`, `meditation`, `stretching`, `bootcamp`, `walking`, `cardio` or `outdoor`
- `content_format`, `instructor_id`, `is_favorite_ride`
- `sort_by` (`original_air_time`, for example) and `desc`
- `limit` and `page`

```bash
# Your 20 newest bookmarked cycling classes
pt "$API/api/v2/ride/archived?browse_category=cycling&is_favorite_ride=true&sort_by=original_air_time&desc=true&limit=20&page=0"
```

```json
{
  "data": [
    {"id": "bbbb2222cccc3333dddd4444eeee5555", "title": "30 min Pop Ride",
     "duration": 1800, "instructor_id": "cccc3333dddd4444eeee5555ffff6666",
     "fitness_discipline": "cycling", "original_air_time": 1761998400,
     "difficulty_rating_avg": 7.8}
  ],
  "instructors": [{"id": "cccc3333dddd4444eeee5555ffff6666", "name": "Coach Example"}],
  "class_types": [{"id": "f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1", "name": "Music"}],
  "page": 0, "page_count": 120, "limit": 20, "total": 2400, "show_next": true
}
```

### `GET /api/v3/ride/live`

The live and encore schedule.

**Auth:** Token + Platform · **Source:** Undocumented

**Params:**

- `start` and `end` (Unix seconds)
- `browse_category`, `content_provider=studio`, `limit`
- `exclude_complete`, `exclude_live_in_studio_only`, `ignore_class_language_preferences`

```bash
start=$(date +%s); end=$((start + 7*24*3600))
pt "$API/api/v3/ride/live?start=$start&end=$end&content_provider=studio&exclude_complete=true&exclude_live_in_studio_only=true"
```

### `GET /api/browse_categories`

The library's top-level categories.

**Auth:** None · **Source:** Undocumented (the spec has an example, but it is not reproduced here)

```bash
pt "$API/api/browse_categories?library_type=on_demand"
```

### `POST /api/favorites/create`

Bookmarks a class. An empty response means it worked.

**Auth:** Token + Platform · **Source:** Spec · **Body:** `ride_id`

```bash
pt -X POST "$API/api/favorites/create" -d '{"ride_id": "bbbb2222cccc3333dddd4444eeee5555"}'
```

### `POST /api/favorites/delete`

Removes a bookmark.

**Auth:** Token · **Source:** Undocumented (Postman collection only) · **Body:** `ride_id`

```bash
pt -X POST "$API/api/favorites/delete" -d '{"ride_id": "bbbb2222cccc3333dddd4444eeee5555"}'
```

### `POST /api/reservation`

Signs you up for a live or encore class. `peloton_id` is the scheduled class's ID from `/api/v3/ride/live`, not the ride ID.

**Auth:** Token + Platform · **Source:** Spec · **Body:** `user_id`, `peloton_id`, `location`

```bash
pt -X POST "$API/api/reservation" \
  -d '{"user_id": "0123456789abcdef0123456789abcdef", "peloton_id": "eeee5555ffff6666aaaa7777bbbb8888", "location": "home"}'
```

```json
{
  "id": "eeee5555ffff6666aaaa7777bbbb8888",
  "peloton_id": "eeee5555ffff6666aaaa7777bbbb8888",
  "user_id": "0123456789abcdef0123456789abcdef",
  "join_token": "exampleJoinToken"
}
```

The `location` value is a guess: the sources name the field but not its values.

### `DELETE /api/reservation/{reservation_id}`

Cancels a reservation.

**Auth:** Token + Platform · **Source:** Spec

```bash
pt -X DELETE "$API/api/reservation/eeee5555ffff6666aaaa7777bbbb8888"
```

```json
{"deleted": true}
```

### `GET /api/peloton/{reservation_id}`

The status of a scheduled class you reserved: whether it is upcoming, live or over.

**Auth:** Token + Platform · **Source:** Undocumented (the spec has an example, but it is not reproduced here)

```bash
pt "$API/api/peloton/eeee5555ffff6666aaaa7777bbbb8888"
```

---

## Instructors

### `GET /api/instructor`

Every instructor, with bio, photo and disciplines.

**Auth:** None · **Source:** Undocumented. The spec's instructor schema is a copy of its member-profile schema, so the fields below are typical but not verified. · **Params:** `page` (from 0), `limit`

```bash
pt "$API/api/instructor?limit=100&page=0"
```

```json
{
  "data": [
    {"id": "cccc3333dddd4444eeee5555ffff6666", "name": "Coach Example",
     "first_name": "Coach", "last_name": "Example",
     "bio": "Example bio.", "image_url": "https://example.com/coach.jpg",
     "fitness_disciplines": ["cycling", "strength"]}
  ],
  "page": 0, "page_count": 1, "limit": 100, "total": 52
}
```

### `GET /api/instructor/{instructor_id}`

One instructor. The response is one entry from the list above.

**Auth:** None · **Source:** Undocumented

```bash
pt "$API/api/instructor/cccc3333dddd4444eeee5555ffff6666"
```

---

## Challenges

### `GET /api/user/{user_id}/challenges/current`

Challenges running now, each with your progress, your current tier, the next tier and how far you have to go. Each value comes formatted for display (`"5,503"`, `"min"`) as well as raw.

**Auth:** Token + Platform · **Source:** Tested (2026-11-14) · **Params:** `has_joined=true` (only the challenges you joined) or `false` (every running challenge, joined or not)

```bash
pt "$API/api/user/$PELOTON_USER/challenges/current?has_joined=true"
```

```json
{
  "challenges": [
    {
      "challenge_summary": {
        "id": "dddd4444eeee5555ffff6666aaaa7777",
        "title": "The Annual 2026",
        "description": "Put in the time and make every minute count",
        "type": "metric",
        "challenge_type": "individual",
        "challenge_audience_type": "global",
        "status": "current",
        "start_time": 1767225600,
        "end_time": 1798761599,
        "fitness_disciplines": null,
        "symbol_image_url": "https://example.com/symbol.png",
        "background_image_url": "https://example.com/background.png"
      },
      "participants": {"total_count": 650000},
      "progress": {
        "has_joined": true,
        "metric_value": 5503,
        "metric_display_value": "5,503",
        "metric_display_unit": "min",
        "metric_display_value_to_next_tier": "497",
        "metric_display_unit_to_next_tier": "min",
        "current_tier": {"id": "t5", "title": "5K", "metric_value": 5000.0,
                         "metric_display_value": "5,000", "metric_display_unit": "min",
                         "has_reward": true, "simple_badge_image_url": "https://example.com/5k.png"},
        "next_tier": {"id": "t6", "title": "6K", "metric_value": 6000.0,
                      "metric_display_value": "6,000", "metric_display_unit": "min",
                      "has_reward": true, "simple_badge_image_url": "https://example.com/6k.png"}
      }
    }
  ],
  "next": {},
  "previous": {},
  "user": {"id": "0123456789abcdef0123456789abcdef", "username": "RiderOne"}
}
```

- **Units vary by challenge:** `min`, `workouts`, `days`, `miles`, `meters` or `reps`.
- **Before the first tier,** `current_tier.title` is `"Unearned"`.
- **Some challenges count only certain classes.** A "Countdown to Turkey Burn" challenge counted only that series' 18 classes, so it showed 0 even after a month of other workouts. `challenge_detail.criteria_description` on the detail call below says what counts.
- **`fitness_disciplines` was `null`** on every challenge seen, including the cycling and rowing ones, so use the unit and title to tell them apart.

### `GET /api/user/{user_id}/challenges/upcoming`

Challenges that haven't started.

**Auth:** Token + Platform · **Source:** Undocumented · **Params:** `has_joined`

```bash
pt "$API/api/user/$PELOTON_USER/challenges/upcoming?has_joined=false"
```

### `GET /api/user/{user_id}/challenges/past`

Finished challenges.

**Auth:** Token + Platform · **Source:** Undocumented (Postman collection only) · **Params:** `has_joined=true`

```bash
pt "$API/api/user/$PELOTON_USER/challenges/past?has_joined=true"
```

### `GET /api/user/{user_id}/challenge/{challenge_id}`

One challenge with every tier and what counts toward it. Note the **singular** `challenge`: the plural `/challenges/{id}` returns `400`.

**Auth:** Token + Platform · **Source:** Tested (2026-11-14)

```bash
pt "$API/api/user/$PELOTON_USER/challenge/dddd4444eeee5555ffff6666aaaa7777"
```

The response has the same `challenge_summary`, `participants`, `progress` and `user` as one entry of `challenges/current`, plus `challenge_detail`:

```json
{
  "challenge_detail": {
    "criteria_description": "Minutes of any class or Just Work Out, on any device.",
    "full_criteria_description": "Every minute of exercise counts toward this challenge.",
    "detailed_description": "Example description.",
    "tiers": [
      {"id": "t0", "title": "Unearned", "metric_value": 0.0},
      {"id": "t1", "title": "1K", "metric_value": 1000.0},
      {"id": "t5", "title": "5K", "metric_value": 5000.0},
      {"id": "t6", "title": "6K", "metric_value": 6000.0},
      {"id": "t20", "title": "20K", "metric_value": 20000.0}
    ]
  }
}
```

The tiers are uneven, so read them and don't assume a step. The real Annual 2026 went 1K to 10K in steps of 1,000, then 15K, 18K and 20K. A title can carry a trailing space (`"1K "`), so trim it.

### `GET /api/user/{user_id}/challenges/{challenge_id}/friends`

How people you follow are doing in a challenge.

**Auth:** Token + Platform · **Source:** Undocumented

This is the plural form, as the spec gives it. The detail call above needs the singular, so try `/challenge/{id}/friends` if this one returns `400`.

```bash
pt "$API/api/user/$PELOTON_USER/challenges/dddd4444eeee5555ffff6666aaaa7777/friends"
```

### `POST /api/user/{user_id}/challenges/{challenge_id}/join`

Joins a challenge. The response is an empty 200.

**Auth:** Token + Platform · **Source:** Spec

```bash
pt -X POST "$API/api/user/$PELOTON_USER/challenges/dddd4444eeee5555ffff6666aaaa7777/join"
```

### `POST /api/user/{user_id}/challenges/{challenge_id}/leave`

Leaves a challenge. The response is an empty 200.

**Auth:** Token + Platform · **Source:** Spec

```bash
pt -X POST "$API/api/user/$PELOTON_USER/challenges/dddd4444eeee5555ffff6666aaaa7777/leave"
```

---

## GraphQL (tags)

Every request is a `POST` to `https://gql-graphql-gateway.prod.k8s.onepeloton.com/graphql`. The body is JSON `{"operationName", "query", "variables"}`. It needs the bearer token, and the community collection also sends `peloton-platform: web`. The `pt` helper sends both.

**Auth:** Token + Platform · **Source:** Undocumented (the Postman collection has the operation names; the queries below are a sketch, not a tested schema)

| Operation | What it does |
|---|---|
| `MyTags` (query) | The tags you've joined. |
| `PrimaryTag` (query) | A member's main tag (variable `userId`). |
| `SearchTag` (query) | Finds tags by name. |
| `TagDetail` (query) | One tag: member count and description. |
| `TagBrowseCategory` (query) | Tag lists. `categorySlug` is `FEATURED`, `FRIENDS`, `POPULAR` or `TRENDING`. |
| `TagBrowseCategoryDisplayNames` (query) | The names of those lists. |
| `AddTagToUser` (mutation) | Joins a tag. |
| `RemoveTagFromUser` (mutation) | Leaves a tag. |
| `SetTagAsPrimary` (mutation) | Makes a tag your main one. |

```bash
pt -X POST https://gql-graphql-gateway.prod.k8s.onepeloton.com/graphql \
  -d '{"operationName": "PrimaryTag",
       "variables": {"userId": "0123456789abcdef0123456789abcdef"},
       "query": "query PrimaryTag($userId: ID!) { user(id: $userId) { primaryTag { name } } }"}'
```

The exact query text lives in `graphql.postman_collection.json` in the Postman repo. Copy it from there, not from the sketch above.

---

## Gotchas

- **Rate limits are unpublished.** Page through workouts with a sensible `limit` (the board's recent fetch uses 20, `recent_fetch_size`) and cache what never changes. A finished workout's details and performance graph don't change.
- **The list and the single workout differ.** `/api/workout/{id}` has 27 top-level keys. The rows in `/workouts` have 24, missing `total_leaderboard_users` and `leaderboard_rank`.
- **Connected equipment.** Workouts from a Bluetooth treadmill or other connected equipment come back with `is_3p_digital_workout` and their own `metrics_type`. Their stats can be thinner than those from Peloton hardware (see `docs/DATA-POINTS.md`).
- **Fields come and go.** Validate everything you read, because a field can be missing, `null` or a different type.
- **Writes are real.** The POST, PUT and DELETE examples change your account. Try the GET calls first.

## Sources

- [DovOps unofficial OpenAPI spec 0.3.0 (SwaggerHub)](https://app.swaggerhub.com/apis/DovOps/peloton-unofficial-api/0.3.0)
- [ostranme/peloton-postman](https://github.com/ostranme/peloton-postman) (Postman collections, including the GraphQL tags)
- [geudrik/peloton-client-library, API_DOCS.md](https://github.com/geudrik/peloton-client-library/blob/master/API_DOCS.md)
- [philosowaffle/peloton-to-garmin, ApiClient.cs](https://github.com/philosowaffle/peloton-to-garmin/blob/master/src/Peloton/ApiClient.cs)
- [peloton-to-garmin discussion #822 (November 2025)](https://github.com/philosowaffle/peloton-to-garmin/discussions/822)
- This repo: `peloton/api.py` (the board's calls), `peloton/summaries.py`, `peloton/records.py`, `peloton/totals.py` and `peloton/workout_features.py` (the fields it reads), and `scripts/refresh_cookies.py` (Auth0 login and renewal)

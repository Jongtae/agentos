# KakaoMap (카카오맵) links

Source: Kakao Maps API guide, "URL로 사용하기", https://apis.map.kakao.com/web/guide/ (checked 2026-10-05). The links are keyless web links. On a phone with KakaoMap installed they open in the app.

Base: `https://map.kakao.com`

| Purpose | Pattern |
| --- | --- |
| Route to a destination | `/link/to/{name},{lat},{lng}` |
| Route to a place id | `/link/to/{placeId}` |
| Route from A to B | `/link/from/{name},{lat},{lng}/to/{name},{lat},{lng}` |
| Route with a mode | `/link/by/{mode}/{name},{lat},{lng}/{name},{lat},{lng}` (start first; up to 5 waypoints between) |
| Subway | `/link/by/subway/{region}/{fromStation}/{toStation}` |
| Show a place | `/link/map/{name},{lat},{lng}` or `/link/map/{placeId}` |
| Search | `/link/search/{query}` |

- `{mode}` is one of `car` (자동차), `traffic` (대중교통), `walk` (도보) and `bicycle` (자전거). `traffic` takes no waypoints.
- `{placeId}` is the number in a KakaoMap place page address, `https://place.map.kakao.com/{placeId}`. A web search for the place often returns that page.
- URL-encode names (spaces and Korean). Use decimal degrees for coordinates.
- Without a start, `/link/to/…` lets KakaoMap use the phone's current position. That is usually what the owner wants on the move.

Example from the guide (car):
`https://map.kakao.com/link/by/car/에이치스퀘어,37.402056,127.108212/카카오판교아지트,37.3952969470752,127.110449292622`

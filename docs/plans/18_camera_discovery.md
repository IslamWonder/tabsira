# 18 · Camera discovery «اكتشف البصائر حولك»

**Phase:** 2 · **Priority:** Low · **Status:** 🔄 · **Updated:** 2026-10-04 19:55 (Tunis)

Point the camera to discover insights shared nearby.

| Step                               | Status | Notes                                                                                                 |
| ---------------------------------- | ------ | ----------------------------------------------------------------------------------------------------- |
| Level A (places) and B (direction) | 🔄     | Task 18.1: built at `/atlas/camera` behind `FEATURE_CAMERA_DISCOVERY`, not yet tested on real phones. |
| Level C (anchoring)                | ⏸      | Behind a switch until proven on devices.                                                              |

**How we check it**

- Tested on real phones.

## Tasks

### 18.1 Camera discovery levels A and B

- **Status:** 🔄 built 2026-10-04 19:55, owners' agent (branch task/18.1-camera-discovery); not yet tested on real phones
- **Goal:** Places around and direction.
- **Depends on:** 17.1
- **Touches:** apps/web camera view.
- **Done when:** Tested on real phones.
- **What was built:** `/atlas/camera` («اكتشف البصائر حولك»), reached from the atlas by «اكتشف بالكاميرا»; the web server reads `FEATURE_CAMERA_DISCOVERY` on every request (`featureCameraDiscovery`), so the page is a 404 and the button is absent while it is off, as the API's `feature()` dependency does for its routes. Level A: on one tap the back camera is shown (`getUserMedia`, never read, drawn or sent; stopped when the page is hidden or left) and the position is watched on the device; the atlas is asked for the existing window endpoint `GET /atlas/entries` around the device, widened to the atlas grid as every window is (no new endpoint; the exact position never leaves the device), and the entries are measured, filtered to the radius and sorted by distance on the device; at most five labels over the view, the rest in the list, which is the keyboard and screen-reader path. Distances are never finer than an entry's cell («أنت بالقرب من منطقتها» inside it). Level B: on a second tap the orientation sensors give the back camera's heading (absolute Euler angles through the DeviceOrientation rotation matrix, or Safari's compass heading turned by the screen angle; a relative alpha is never a heading), smoothed and paced, with hysteresis for «في اتجاه الكاميرا» (an obstructed place is never called visible: extension §6B); an arrow and a sector word point toward each entry's area, never toward a thing, only beyond the entry's own cell; no reading within 4 s, a refusal, a lost reading or a fix looser than 500 m falls back to level A with «العرض بحسب المنطقة». Refusing the camera keeps the list and the map; refusing the position offers a place search labelled «استكشاف المنطقة المختارة» with no distances; readings older than a minute are ignored; the atlas is asked again only after a real move (a quarter of the radius, at least 250 m), a widening or a new centre. No filters, no level C, no developer diagnostics screen.
- **For the owners to test on phones:** Android Chrome (`deviceorientationabsolute`) and iOS Safari (`requestPermission`, `webkitCompassHeading`, the screen-angle correction in landscape), over https only (plain http at `tabsira.test` has no camera and no sensors: decision 49); the arrow's sense (left/right) and the 100 ms pacing; battery over a few minutes; the camera stopping when switching apps and resuming on «أعد تشغيل الكاميرا».
- **Left for the owners:** the privacy text already says the camera discovery uses the device's position with permission and that the live position is not kept; it does not yet say that the camera's video and the sensors' readings stay on the device. Adding that sentence changes the privacy policy's version (decision 35), so it is left to the owners.

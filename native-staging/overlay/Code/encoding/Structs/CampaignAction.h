#pragma once
#include <cstdint>
enum class CampaignAction : uint8_t { Join, Acquire, Renew, Release, FollowerClaim, FollowerPermission, FollowerFollow, FollowerWait, FollowerDismiss, FollowerDead, FollowerSeen, FollowerSeenWaiting, SessionExpired, SessionState };

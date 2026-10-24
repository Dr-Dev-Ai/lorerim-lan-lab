#include <TiltedCore/Stl.hpp>
#include <TiltedCore/Allocator.hpp>
#include <TiltedCore/Buffer.hpp>
#include <TiltedCore/Serialization.hpp>
#include <glm/vec2.hpp>
#include <glm/vec3.hpp>
#include <optional>
#include <catch2/catch.hpp>
#include <Messages/ClientMessageFactory.h>
#include <Messages/ServerMessageFactory.h>
using namespace TiltedPhoques;

template<class T, class Factory> void RoundTrip(const T& original)
{
    Buffer buffer(65536);
    Buffer::Writer writer(&buffer);
    original.Serialize(writer);
    Buffer::Reader reader(&buffer);
    auto message = Factory{}.Extract(reader);
    REQUIRE(message);
    REQUIRE(message->GetOpcode() == original.GetOpcode());
    auto decoded = CastUnique<T>(std::move(message));
    REQUIRE(*decoded == original);
}

TEST_CASE("LAN drop claims preserve transaction identity", "[encoding.lan]")
{
    for (const int32_t count : {-11, 0, 37})
    {
        RequestInventoryChanges request;
        request.DroppedId = 0xFEDCBA9876543210ULL;
        request.ClaimId = 0x123456789ABCDEF0ULL;
        request.ServerId = 359;
        request.OwnershipEpoch = 1234;
        request.Item.BaseId = {3492, 0xABCD};
        request.Item.Count = count;
        request.Item.ExtraCharge = 24.5f;
        request.Item.EnchantData.IsWeapon = true;
        Inventory::EffectItem effect;
        effect.EffectId = {3489, 0x9876};
        effect.Magnitude = 17.5f;
        effect.Duration = 300;
        request.Item.EnchantData.Effects.push_back(effect);
        request.Drop = true;
        request.UpdateClients = false;
        RoundTrip<RequestInventoryChanges, ClientMessageFactory>(request);
        NotifyInventoryChanges notification;
        notification.DroppedId = request.DroppedId;
        notification.ClaimId = request.ClaimId;
        notification.ServerId = request.ServerId;
        notification.OwnershipEpoch = request.OwnershipEpoch;
        notification.Item = request.Item;
        notification.Drop = true;
        RoundTrip<NotifyInventoryChanges, ServerMessageFactory>(notification);
    }
}

TEST_CASE("LAN rest messages preserve every action", "[encoding.lan]")
{
    for (uint8_t action = 0; action <= static_cast<uint8_t>(PartyRestAction::Complete); ++action)
    {
        PartyRestRequest request;
        request.Session = 0xFEDCBA9876543210ULL;
        request.Action = static_cast<PartyRestAction>(action);
        request.Hours = 24.f;
        request.AdvanceTime = true;
        request.Benefit = action % 4;
        RoundTrip<PartyRestRequest, ClientMessageFactory>(request);
        NotifyPartyRest notification;
        notification.Session = request.Session;
        notification.Action = request.Action;
        notification.Hours = 1.f;
        notification.AdvanceTime = false;
        notification.Benefit = request.Benefit;
        RoundTrip<NotifyPartyRest, ServerMessageFactory>(notification);
    }
}

TEST_CASE("LAN object animations retain translated object and cell", "[encoding.lan]")
{
    ScriptAnimationRequest request;
    request.Id = {3491, 0x12345};
    request.CellId = {17, 0x2468};
    request.Animation = String("LANTestSawmillAnimation");
    request.EventName = String("LANTestAnimationEnd");
    RoundTrip<ScriptAnimationRequest, ClientMessageFactory>(request);
    NotifyScriptAnimation notification;
    notification.Id = request.Id;
    notification.CellId = request.CellId;
    notification.Animation = request.Animation;
    notification.EventName = request.EventName;
    RoundTrip<NotifyScriptAnimation, ServerMessageFactory>(notification);
}

TEST_CASE("Campaign permission messages preserve correlation and actor identity", "[encoding.lan]")
{
    for (uint8_t action = 0; action <= static_cast<uint8_t>(CampaignAction::SessionState); ++action)
    {
        CampaignActionRequest request;
        request.RequestId = 0xFEDCBA9876543210ULL;
        request.Actor = {3491, 0xA2C94};
        request.Action = static_cast<CampaignAction>(action);
        request.Credential = "synthetic-test-credential";
        request.SaveProof = "synthetic-save-proof";
        RoundTrip<CampaignActionRequest, ClientMessageFactory>(request);
        NotifyCampaignAction notify;
        notify.RequestId = request.RequestId; notify.Actor = request.Actor; notify.Action = request.Action;
        notify.Epoch = "epoch"; notify.Checkpoint = "checkpoint"; notify.Revision = 0xFEDCBA9876543210ULL;
        notify.Enabled = true; notify.Allowed = action % 2; notify.IsLeader = true;
        RoundTrip<NotifyCampaignAction, ServerMessageFactory>(notify);
    }
}
TEST_CASE("Authentication retains the required campaign guard flag", "[encoding.lan]")
{
    AuthenticationRequest request;
    request.CampaignGuard = true;
    request.Username = "Synthetic player";
    RoundTrip<AuthenticationRequest, ClientMessageFactory>(request);
}

TEST_CASE("Campaign follower policy preserves simulator epoch and replay sequence", "[encoding.lan]")
{
    for (uint8_t policy : {1, 2, 3})
    {
        NotifyCampaignFollower message;
        message.Actor = {3491, 0xABCDEF};
        message.OwnershipEpoch = 0xFEDCBA98;
        message.Sequence = 0xFEDCBA9876543210ULL;
        message.Policy = policy;
        RoundTrip<NotifyCampaignFollower, ServerMessageFactory>(message);
    }
}

TEST_CASE("Co-op checkpoint chunks preserve request correlation and bounded payload", "[encoding.lan]")
{
    RequestCampaignCheckpoint request;request.RequestId=0xFEDCBA9876543210ULL;
    request.Payload=String(40000,'A');RoundTrip<RequestCampaignCheckpoint,ClientMessageFactory>(request);
    NotifyCampaignCheckpoint response;response.RequestId=request.RequestId;response.Payload="ack";
    RoundTrip<NotifyCampaignCheckpoint,ServerMessageFactory>(response);
}

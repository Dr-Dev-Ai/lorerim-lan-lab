#pragma once
#include <Events/PacketEvent.h>
#include <Structs/PartyRestAction.h>
struct World;
struct UpdateEvent;
struct PartyRestRequest;
struct Player;

class PartyRestService
{
public:
    PartyRestService(World&, entt::dispatcher&);
private:
    struct Session
    {
        uint64_t Id{};
        uint32_t Leader{};
        float Hours{};
        uint64_t Deadline{};
        bool Finished{};
        bool Unpartied{};
        uint8_t Benefit{};
        Vector<uint32_t> Members;
        Map<uint32_t, uint64_t> ReadyAt;
    };
    void OnRequest(const PacketEvent<PartyRestRequest>&) noexcept;
    void OnUpdate(const UpdateEvent&) noexcept;
    bool MembershipMatches(const Session&) noexcept;
    void Broadcast(const Session&, PartyRestAction, bool aAdvance = false) noexcept;
    World& m_world;
    uint64_t m_nextSession{1};
    Map<uint32_t, Session> m_sessions;
    entt::scoped_connection m_requestConnection;
    entt::scoped_connection m_updateConnection;
};

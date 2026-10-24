#pragma once
#include <atomic>
#include <mutex>
#include <Structs/Inventory.h>
struct ActiveEffect;
struct World;
struct TransportService;
struct UpdateEvent;
struct DisconnectedEvent;
struct NotifyPartyRest;
struct PartyRestCommandEvent;

class PartyRestService
{
public:
    PartyRestService(World&, entt::dispatcher&, TransportService&);
    // Papyrus worker threads only exchange an atomic value or queue a command.
    static float Exchange(float aCommand) noexcept;
    static int32_t NextEquipmentActor() noexcept;
private:
    void OnCommand(const PartyRestCommandEvent&) noexcept;
    void OnNotify(const NotifyPartyRest&) noexcept;
    void OnUpdate(const UpdateEvent&) noexcept;
    void OnDisconnected(const DisconnectedEvent&) noexcept;
    void Send(uint8_t aAction, float aHours = 0.f, uint8_t aBenefit = 0) noexcept;
    void CaptureTimedEffects() noexcept;
    void RefreshEquipmentDisplays() noexcept;
    void ApplyTimedEffects(float aHours) noexcept;
    struct TimedEffect
    {
        const ActiveEffect* pEffect{};
        uint16_t UniqueId{};
        float Elapsed{};
    };
    Vector<TimedEffect> m_timedEffects;
    float m_restTimeScale{};
    bool m_localRest{};
    World& m_world;
    TransportService& m_transport;
    uint64_t m_session{};
    uint64_t m_lastReceipt{};
    uint64_t m_nextReport{};
    bool m_pendingStatsMenu{};
    uint64_t m_nextEquipmentRefresh{};
    Map<uint32_t, Inventory> m_displayInventories;
    static std::mutex s_displayMutex;
    static Vector<uint32_t> s_displayQueue;
    static std::atomic<uint8_t> s_pendingBenefit;
    static std::atomic<float> s_pendingHours;
    static std::atomic<bool> s_isLeader;
    static std::atomic<bool> s_connected;
    entt::scoped_connection m_commandConnection;
    entt::scoped_connection m_notifyConnection;
    entt::scoped_connection m_updateConnection;
    entt::scoped_connection m_disconnectConnection;
};

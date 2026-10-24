#pragma once
#include <array>
#include <mutex>
#include <atomic>
#include <Structs/TimeModel.h>

struct World;
struct TransportService;
struct ImguiService;
struct UpdateEvent;
struct ConnectedEvent;
struct DisconnectedEvent;
struct ServerTimeSettings;

// Observe on UpdateEvent; render a copied snapshot without touching the ECS.
struct SyncHealthService
{
    SyncHealthService(World&, entt::dispatcher&, TransportService&, ImguiService&);
    void NoteConnectedLoad() noexcept;

private:
    struct ActorSample
    {
        uint32_t Form{}, Server{};
        double Age{}, Jitter{}, Delay{};
        bool Extrapolating{};
    };
    struct Snapshot
    {
        bool Connected{}, ClockReady{}, LoadedOnline{}, Paused{}, Checkpoint{};
        int Ping{-1}, PendingBytes{};
        float QualityIn{-1.f}, QualityOut{-1.f}, InKB{}, OutKB{};
        double SampledAt{}, PollAge{}, QueueMs{}, FrameMs{}, ServerReportAge{-1.}, ClockErrorSeconds{};
        uint32_t RemoteActors{}, StaleActors{}, Extrapolating{}, LocalActors{};
        uint64_t Corrections{}, Snaps{}, Stalls{};
        float LargestCorrection{};
        std::array<ActorSample, 5> Actors{};
        size_t ActorRows{};
    };
    void OnUpdate(const UpdateEvent&) noexcept;
    void OnDraw() noexcept;
    void OnConnected(const ConnectedEvent&) noexcept;
    void OnDisconnected(const DisconnectedEvent&) noexcept;
    void OnTime(const ServerTimeSettings&) noexcept;
    static double Now() noexcept;

    World& m_world;
    TransportService& m_transport;
    entt::scoped_connection m_update, m_draw, m_connected, m_disconnected, m_time;
    std::mutex m_mutex;
    Snapshot m_snapshot;
    std::array<float, 120> m_pingHistory{}, m_ageHistory{};
    size_t m_historyCount{}, m_historyNext{};
    double m_nextSample{}, m_nextHistory{}, m_connectedAt{}, m_reportAt{}, m_reportNetworkAt{};
    TimeModel m_serverTime{};
    uint64_t m_stalls{};
    bool m_loadedOnline{}, m_keyDown{};
    std::atomic<double> m_lastUpdateAt{0.};
    int m_mode{1}, m_toggleKey{0x79}, m_x{24}, m_y{150};
    float m_fontScale{1.25f};
};

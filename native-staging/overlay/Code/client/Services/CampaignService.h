#pragma once
#include <atomic>
#include <mutex>
#include <unordered_map>
#include <deque>
#include <thread>
#include <filesystem>
#include <CampaignSave.h>
#include <array>
#include <Messages/CampaignActionRequest.h>
struct World; struct TransportService; struct ConnectedEvent; struct DisconnectedEvent;
struct CampaignFollowerEvent; struct NotifyCampaignFollower;
struct UpdateEvent; struct NotifyCampaignAction; struct CampaignInteractionEvent;
class CampaignService
{
public:
    CampaignService(World&, entt::dispatcher&, TransportService&);
    ~CampaignService();
    void BeginAttach(uint32_t aPlayerId) noexcept;
    static bool IsAdmitted() noexcept;
    static void CheckpointPhase(uint32_t) noexcept;
    static bool IsCheckpointActive() noexcept;
    static bool IsCheckpointFrozen() noexcept;
    static bool IsCheckpointSealed() noexcept;
    static bool CheckpointUnsafe() noexcept;
    static void NoteCheckpointMutation(bool aRemote) noexcept;
    bool CheckpointQuiet() const noexcept;
    static void NoteOfflineMutation() noexcept;
    static void BeforeSaveLoad() noexcept;
    static void SuspendForLoad() noexcept;
    static bool IsConfigured() noexcept;
    // Called before local activation/menu fragments. Hooks only read a cache and
    // queue a main-thread event; they never access files or wait on the network.
    static int32_t NextFollowerPolicy() noexcept;
    static int32_t Follower(int32_t aFormId, int32_t aCommand) noexcept;
    static bool Gate(uint32_t aActorFormId, bool aReplayActivation) noexcept;
private:
    void OnConnected(const ConnectedEvent&) noexcept;
    void OnDisconnected(const DisconnectedEvent&) noexcept;
    void OnFollowerPolicy(const NotifyCampaignFollower&) noexcept;
    void OnFollower(const CampaignFollowerEvent&) noexcept;
    void OnInteraction(const CampaignInteractionEvent&) noexcept;
    void OnNotify(const NotifyCampaignAction&) noexcept;
    void OnUpdate(const UpdateEvent&) noexcept;
    void Send(CampaignAction, const GameId& = {});
    static uint64_t Now() noexcept;
    World& m_world;
    TransportService& m_transport;
    String m_credential, m_saveProof;
    std::filesystem::path m_saveDirectory;
    CampaignSave::Read m_saveRead{};
    CampaignSave::SetHead m_saveSetHead{};
    CampaignSave::Snapshot m_saveSnapshot;
    std::thread m_saveThread;
    std::atomic<bool> m_proofDone{false};
    bool m_proofValid{}, m_attachPending{};
    uint32_t m_attachPlayer{};
    uint64_t m_attachDeadline{}, m_usedGeneration{UINT64_MAX};
    uint64_t m_progressGeneration{UINT64_MAX}, m_nextProgressCheck{};
    std::array<float,38> m_progressBaseline{};
    bool m_ready{};
    uint64_t m_sequence{};
    uint64_t m_pending{};
    uint32_t m_pendingForm{};
    bool m_replay{};
    GameId m_actor{};
    uint64_t m_nextRenew{};
    bool m_hadMenu{};
    static std::atomic<CampaignSave::Read> s_identityRead;
    static std::atomic<uint32_t> s_checkpointPhase;
    static std::atomic<bool> s_checkpointUnsafe;
    static std::atomic<uint64_t> s_checkpointMutation;
    static std::atomic<bool> s_configured, s_active, s_admitted, s_saveInvalidated, s_offlineDirty;
    static std::mutex s_mutex;
    static uint32_t s_actor;
    static uint64_t s_until, s_nextRequest;
    struct FollowerAnswer { CampaignAction Action{}; uint64_t Until{}; int32_t Answer{}; };
    struct FollowerRequest { uint32_t FormId{}; CampaignAction Action{}; uint64_t Until{}; };
    static std::unordered_map<uint32_t, FollowerAnswer> s_followers;
    std::unordered_map<uint64_t, FollowerRequest> m_followerPending;
    struct PendingPolicy { uint32_t Epoch{}; uint64_t Sequence{}, Until{}, NextDelivery{}; uint8_t State{}; bool Queued{}, Verified{}; };
    static std::unordered_map<uint32_t, PendingPolicy> s_policies;
    static std::deque<uint32_t> s_policyQueue;
    entt::scoped_connection m_followerPolicy;
    entt::scoped_connection m_follower;
    entt::scoped_connection m_connected, m_disconnected, m_interaction, m_notify, m_update;
};

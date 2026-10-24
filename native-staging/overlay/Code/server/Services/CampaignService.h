#pragma once
#include <Events/PacketEvent.h>
#include <Messages/CampaignActionRequest.h>
#include <Messages/NotifyCampaignAction.h>
#include <condition_variable>
#include <deque>
#include <mutex>
#include <thread>
#include <vector>
#include <DateTime.h>
#include <unordered_map>
struct World;
struct UpdateEvent;
struct PlayerLeaveEvent;
struct Player;

// Main-thread authority and a bounded, asynchronous loopback adapter. No engine
// hook or server update performs blocking HTTP.
class CampaignService
{
public:
    CampaignService(World&, entt::dispatcher&);
    ~CampaignService();
    static bool IsRequired() noexcept;
    int ApiPort() const noexcept { return m_apiPort; }
    std::string CredentialFor(const Player*) const;
    bool HasPendingWorldChanges() const noexcept { return m_worldChangePending || m_worldChangeQueued; }
    void NoteWorldChange() noexcept;
    bool IsAdmitted(const Player*) const noexcept;
    void StageJoin(Player*, const GameId&, const GameId&, const DateTime&);
    bool CanQuest(const Player*) const noexcept;
    bool CanClaimFollower(const Player*, const GameId&) const noexcept;
    bool CanInteract(const Player*, const GameId&) const noexcept;
private:
    struct Job
    {
        uint32_t Player{};
        CampaignActionRequest Request;
        std::string Credential;
        std::string ActorKey;
        std::string LeaseToken;
        uint64_t Generation{};
        bool Disconnect{};
        bool Heartbeat{};
        bool WorldChange{};
        uint64_t WorldSerial{};
        std::string Operation;
        std::string SessionKey;
    };
    struct FollowerPolicy
    {
        std::string Actor, Owner, State;
        uint64_t Version{}, Until{};
        bool Parked{};
    };
    struct Result
    {
        Job Work;
        bool Allowed{};
        bool Leader{};
        std::string StablePlayer, Campaign, Epoch, Checkpoint;
        uint64_t Revision{};
        std::vector<FollowerPolicy> Followers;
        bool FollowerSnapshot{};
        std::string LeaseToken;
        uint64_t Generation{};
    };
    struct Session { std::string Credential; bool Leader{}; uint64_t LatestRequest{}; bool Attached{}; uint64_t LatestDialogue{}; std::string Key; uint64_t Expires{}; uint64_t NextHeartbeat{}; std::string StablePlayer, Campaign; };
    struct Grant { uint32_t Player{}; uint64_t Expires{}; std::string Token; uint64_t Generation{}; };
    void OnRequest(const PacketEvent<CampaignActionRequest>&) noexcept;
    void OnUpdate(const UpdateEvent&) noexcept;
    void OnLeave(const PlayerLeaveEvent&) noexcept;
    void Worker();
    void ReconcileFollowers(uint64_t);
    void CompleteJoin(Player*);
    std::string ActorKey(const GameId&) const;
    bool Queue(Job);
    World& m_world;
    const int m_apiPort;
    std::unordered_map<uint32_t, Session> m_sessions;
    std::unordered_map<std::string, Grant> m_grants;
    std::unordered_map<std::string, FollowerPolicy> m_followers;
    struct PendingJoin { GameId WorldSpace, Cell; DateTime Time; };
    std::unordered_map<uint32_t, PendingJoin> m_pendingJoins;
    bool m_worldChangePending{}, m_worldChangeQueued{};
    uint64_t m_worldSerial{}, m_worldPersistedSerial{}, m_nextWorldRetry{};
    std::string m_campaign;
    uint64_t m_nextFollowerReconcile{}, m_followerSequence{};
    std::mutex m_mutex;
    std::condition_variable m_wake;
    std::deque<Job> m_jobs;
    std::deque<Result> m_results;
    bool m_stop{};
    std::thread m_worker;
    entt::scoped_connection m_requestConnection, m_updateConnection, m_leaveConnection;
};

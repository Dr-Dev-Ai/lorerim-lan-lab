#pragma once
#include <Events/PacketEvent.h>
#include <Messages/RequestCampaignCheckpoint.h>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <deque>
#include <unordered_set>
struct World; struct UpdateEvent; struct PlayerLeaveEvent; struct Player;
// JSON/control and chunk uploads use a separate bounded worker. No disk/HTTP on
// the game server tick. Per-player fences begin only after that peer's pause ACK.
class CampaignCheckpointService
{
public:
    CampaignCheckpointService(World&,entt::dispatcher&);
    ~CampaignCheckpointService();
    bool IsPreparing() const noexcept { return !m_proposal.empty() && m_phase != "committed" && m_phase != "aborted"; }
    bool IsClockFrozen() const noexcept { return m_phase == "saving"; }
    bool IsFrozen(uint32_t player) const noexcept { return m_frozenPeers.contains(player); }
private:
    struct Job { uint32_t Player{}; uint64_t Connection{},Request{}; std::string Credential,Action,Body; };
    struct Result { Job Work; bool Ok{}; std::string Body; };
    void OnRequest(const PacketEvent<RequestCampaignCheckpoint>&) noexcept;
    void OnUpdate(const UpdateEvent&) noexcept;
    void OnLeave(const PlayerLeaveEvent&) noexcept;
    bool Queue(Job);
    void Worker();
    void ApplyStatus(const std::string&);
    void Broadcast(const std::string&);
    void Abort(const std::string&);
    Job LeaderJob(const std::string&,const std::string&);
    World& m_world;
    int m_port;
    std::string m_proposal,m_phase,m_epoch,m_parent,m_leaderCredential,m_abortReason;
    uint64_t m_revision{},m_nextPoll{};
    uint32_t m_leaderId{};
    bool m_controlPending{},m_pollPending{},m_stop{};
    std::unordered_set<uint32_t> m_frozenPeers;
    std::mutex m_mutex; std::condition_variable m_wake;
    std::deque<Job> m_jobs; std::deque<Result> m_results;
    std::thread m_worker;
    entt::scoped_connection m_request,m_update,m_leave;
};

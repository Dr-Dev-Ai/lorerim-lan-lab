#pragma once
#include <thread>
#include <atomic>
#include <mutex>
#include <condition_variable>
#include <filesystem>
#include <CampaignSave.h>
struct World;struct TransportService;struct UpdateEvent;struct DisconnectedEvent;struct NotifyCampaignCheckpoint;
class CampaignCheckpointService
{
public:
    CampaignCheckpointService(World&,entt::dispatcher&,TransportService&);
    ~CampaignCheckpointService();
private:
    void OnNotify(const NotifyCampaignCheckpoint&) noexcept;
    void OnUpdate(const UpdateEvent&) noexcept;
    void OnDisconnected(const DisconnectedEvent&) noexcept;
    void Send(const std::string&,uint64_t=0);
    void Fail(const std::string&);
    void Resume(bool,const std::string&,uint64_t);
    void Upload(std::string,std::filesystem::path,std::filesystem::path);
    World& m_world;TransportService& m_transport;
    std::string m_proposal,m_epoch,m_parent,m_phase,m_uploadBody,m_error;
    uint64_t m_generation{},m_revision{},m_started{},m_sequence{},m_pending{},m_lastSend{},m_expectedReceived{};
    bool m_openedJournal{},m_readySent{},m_ack{},m_uploadAvailable{};
    std::atomic<bool> m_stop{false},m_done{true},m_failed{false};
    CampaignSave::Read m_read{};CampaignSave::SetHead m_setHead{};
    std::filesystem::path m_saves,m_profile;
    std::mutex m_mutex;std::condition_variable m_wake;std::thread m_worker;
    entt::scoped_connection m_notify,m_update,m_disconnect;
};

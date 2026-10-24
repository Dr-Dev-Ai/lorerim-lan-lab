#include <Services/CampaignService.h>
#include <World.h>
#include <Events/ConnectedEvent.h>
#include <Events/DisconnectedEvent.h>
#include <Events/UpdateEvent.h>
#include <Events/CampaignInteractionEvent.h>
#include <Events/CampaignFollowerEvent.h>
#include <Messages/NotifyCampaignFollower.h>
#include <Messages/NotifyCampaignAction.h>
#include <Games/Misc/MenuTopicManager.h>
#include <Games/Skyrim/Interface/UI.h>
#include <Games/Overrides.h>
#include <PlayerCharacter.h>
#include <chrono>
#include <fstream>
#include <cryptopp/sha.h>
#include <Services/InventoryService.h>
std::atomic<bool> CampaignService::s_configured{false}, CampaignService::s_active{false}, CampaignService::s_admitted{false}, CampaignService::s_saveInvalidated{false}, CampaignService::s_offlineDirty{false};
std::atomic<uint32_t> CampaignService::s_checkpointPhase{0};
std::atomic<CampaignSave::Read> CampaignService::s_identityRead{nullptr};
std::atomic<bool> CampaignService::s_checkpointUnsafe{false};
std::atomic<uint64_t> CampaignService::s_checkpointMutation{0};
std::mutex CampaignService::s_mutex;
std::unordered_map<uint32_t, CampaignService::FollowerAnswer> CampaignService::s_followers;
std::unordered_map<uint32_t, CampaignService::PendingPolicy> CampaignService::s_policies;
std::deque<uint32_t> CampaignService::s_policyQueue;
uint32_t CampaignService::s_actor{};
uint64_t CampaignService::s_until{}, CampaignService::s_nextRequest{};
uint64_t CampaignService::Now() noexcept
{
    return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count());
}
bool CampaignService::IsConfigured() noexcept { return s_configured.load(); }
CampaignService::CampaignService(World& world, entt::dispatcher& dispatcher, TransportService& transport) : m_world(world), m_transport(transport)
{
    constexpr const char* path = ".\\Data\\SKSE\\Plugins\\LoreRimCampaign.ini";
    s_configured.store(GetPrivateProfileIntA("Campaign", "Enabled", 0, path) != 0);
    char credential[256]{};
    GetPrivateProfileStringA("Campaign", "Credential", "", credential, sizeof(credential), path);
    m_credential = credential;
    SecureZeroMemory(credential, sizeof(credential));
    wchar_t saveDirectory[2048]{};
    GetPrivateProfileStringW(L"Campaign", L"SaveDirectory", L"", saveDirectory, 2048, L".\\Data\\SKSE\\Plugins\\LoreRimCampaign.ini");
    m_saveDirectory = saveDirectory;
    m_connected = dispatcher.sink<ConnectedEvent>().connect<&CampaignService::OnConnected>(this);
    m_disconnected = dispatcher.sink<DisconnectedEvent>().connect<&CampaignService::OnDisconnected>(this);
    m_interaction = dispatcher.sink<CampaignInteractionEvent>().connect<&CampaignService::OnInteraction>(this);
    m_notify = dispatcher.sink<NotifyCampaignAction>().connect<&CampaignService::OnNotify>(this);
    m_followerPolicy = dispatcher.sink<NotifyCampaignFollower>().connect<&CampaignService::OnFollowerPolicy>(this);
    m_follower = dispatcher.sink<CampaignFollowerEvent>().connect<&CampaignService::OnFollower>(this);
    m_update = dispatcher.sink<UpdateEvent>().connect<&CampaignService::OnUpdate>(this);
}
CampaignService::~CampaignService()
{
    if (m_saveThread.joinable()) m_saveThread.join();
}
bool CampaignService::IsAdmitted() noexcept { return !IsConfigured() || s_admitted.load(); }
void CampaignService::CheckpointPhase(uint32_t phase) noexcept
{
    s_checkpointPhase.store(phase);
    if (phase <= 1)
    {
        s_checkpointUnsafe.store(false); s_checkpointMutation.store(Now());
        std::lock_guard lock(s_mutex); s_policyQueue.clear(); s_policies.clear(); s_actor = 0; s_until = 0;
    }
}
bool CampaignService::IsCheckpointActive() noexcept { return s_checkpointPhase.load() != 0; }
bool CampaignService::IsCheckpointFrozen() noexcept { return s_checkpointPhase.load() >= 2; }
bool CampaignService::IsCheckpointSealed() noexcept { return s_checkpointPhase.load() == 3; }
bool CampaignService::CheckpointUnsafe() noexcept { return s_checkpointUnsafe.load(); }
void CampaignService::NoteCheckpointMutation(bool remote) noexcept
{
    if (!IsCheckpointActive()) return;
    s_checkpointMutation.store(Now());
    if ((IsCheckpointFrozen() && !remote) || IsCheckpointSealed()) s_checkpointUnsafe.store(true);
}
bool CampaignService::CheckpointQuiet() const noexcept
{
    return m_followerPending.empty() && Now() >= s_checkpointMutation.load() + 2000
        && !m_world.ctx().at<InventoryService>().HasPendingDropClaims();
}
void CampaignService::NoteOfflineMutation() noexcept
{
    NoteCheckpointMutation(false);
    if (IsConfigured() && !IsAdmitted())
    {
        // Deserialization is inside the preload barrier, not offline gameplay.
        // Once PostLoad marks the record ready, mod-driven changes count too.
        CampaignSave::Snapshot snapshot;
        const auto read = s_identityRead.load();
        if (read && read(&snapshot,sizeof(snapshot)) && snapshot.Status == CampaignSave::Ready)
            s_offlineDirty.store(true);
    }
}
void CampaignService::BeforeSaveLoad() noexcept
{
    s_offlineDirty.store(false); SuspendForLoad();
}
void CampaignService::SuspendForLoad() noexcept
{
    s_admitted.store(false); s_saveInvalidated.store(true);
    std::lock_guard lock(s_mutex); s_followers.clear(); s_policies.clear(); s_policyQueue.clear(); s_actor = 0; s_until = 0;
}
void CampaignService::BeginAttach(uint32_t playerId) noexcept
{
    m_ready = false; s_admitted.store(false); s_active.store(IsConfigured());
    m_attachPlayer = playerId; m_attachDeadline = Now() + 15000;
    m_sequence = m_pending = 0; m_actor = {}; m_hadMenu = false;
    m_followerPending.clear();
    { std::lock_guard lock(s_mutex); s_followers.clear(); s_policies.clear(); s_policyQueue.clear(); s_actor = 0; s_until = s_nextRequest = 0; }
    auto fail = [&]() { spdlog::error("Campaign admission requires its co-save companion, an initialized/reloaded enrolled save, and SaveDirectory configuration"); m_transport.Close(); };
    if (s_offlineDirty.load())
    {
        spdlog::error("Campaign admission refused because player inventory or quest state changed offline after loading; reload the enrolled checkpoint");
        m_transport.Close(); return;
    }
    auto* module = GetModuleHandleW(L"LoreRimCampaignCosave.dll");
    if (!module || !m_saveDirectory.is_absolute()) { fail(); return; }
    m_saveRead = reinterpret_cast<CampaignSave::Read>(GetProcAddress(module, "LoreRimCampaign_Read"));
    s_identityRead.store(m_saveRead);
    m_saveSetHead = reinterpret_cast<CampaignSave::SetHead>(GetProcAddress(module, "LoreRimCampaign_SetHead"));
    auto registerBarrier = reinterpret_cast<CampaignSave::RegisterBarrier>(GetProcAddress(module, "LoreRimCampaign_RegisterBarrier"));
    if (!m_saveRead || !m_saveSetHead || !registerBarrier || !registerBarrier(&CampaignService::BeforeSaveLoad)
        || !m_saveRead(&m_saveSnapshot, sizeof(m_saveSnapshot)) || m_saveSnapshot.Status != CampaignSave::Ready
        || m_saveSnapshot.Record.Version != CampaignSave::Schema || !m_saveSnapshot.Record.Campaign[0]
        || !m_saveSnapshot.Record.Epoch[0] || m_saveSnapshot.Generation == m_usedGeneration)
    { fail(); return; }
    // The preceding load already finished; only future loads invalidate this attach.
    s_saveInvalidated.store(false);
    if (m_saveThread.joinable())
    {
        if (!m_proofDone.load()) { fail(); return; }
        m_saveThread.join();
    }
    m_proofDone.store(false); m_proofValid = false; m_attachPending = true;
    const auto snapshot = m_saveSnapshot;
    const auto directory = m_saveDirectory;
    m_saveThread = std::thread([this, snapshot, directory]
    {
        auto hash = [](const std::filesystem::path& path) -> std::string
        {
            std::error_code error;
            if (!std::filesystem::is_regular_file(path, error) || error) return {};
            const auto size = std::filesystem::file_size(path, error);
            if (error || !size || size > (uint64_t{2} << 30)) return {};
            const auto modified = std::filesystem::last_write_time(path, error);
            if (error) return {};
            std::ifstream file(path, std::ios::binary);
            if (!file) return {};
            CryptoPP::SHA256 sha;
            char buffer[65536]; uint64_t total = 0;
            while (file)
            {
                file.read(buffer, sizeof(buffer));
                const auto count = file.gcount();
                if (count > 0) { sha.Update(reinterpret_cast<const CryptoPP::byte*>(buffer), static_cast<size_t>(count)); total += static_cast<uint64_t>(count); }
            }
            if (!file.eof() || total != size || std::filesystem::file_size(path, error) != size || error
                || std::filesystem::last_write_time(path, error) != modified || error) return {};
            CryptoPP::byte digest[32]; sha.Final(digest);
            constexpr char hex[] = "0123456789abcdef";
            std::string result(64, '0');
            for (size_t i = 0; i < 32; ++i) { result[2*i] = hex[digest[i] >> 4]; result[2*i+1] = hex[digest[i] & 15]; }
            return result;
        };
        auto name = std::filesystem::path(snapshot.SaveName).filename();
        if (!name.empty())
        {
            auto ess = directory / name; ess.replace_extension(".ess");
            auto skse = ess; skse.replace_extension(".skse");
            const auto essHash = hash(ess), skseHash = hash(skse);
            // Rehash the first pair member after the other to reject an interleaved save.
            if (!essHash.empty() && !skseHash.empty() && hash(ess) == essHash && hash(skse) == skseHash)
            {
                const auto& record = snapshot.Record;
                m_saveProof = fmt::format(R"({{"character":"{}","campaign":"{}","epoch":"{}","checkpoint":"{}","ess_sha256":"{}","skse_sha256":"{}"}})",
                    record.Character, record.Campaign, record.Epoch, record.Checkpoint, essHash, skseHash).c_str();
                m_proofValid = true;
            }
        }
        m_proofDone.store(true);
    });
}
bool CampaignService::Gate(uint32_t actor, bool replay) noexcept
{
    if (IsCheckpointActive()) return false;
    if (!s_active.load()) return true;
    const uint64_t now = Now();
    { std::lock_guard lock(s_mutex);
      if (s_actor == actor && s_until > now) return true;
      if (now < s_nextRequest) return false;
      s_nextRequest = now + 750; }
    World::Get().GetRunner().Trigger(CampaignInteractionEvent{actor, replay});
    return false;
}
int32_t CampaignService::Follower(int32_t formId, int32_t command) noexcept
{
    if (command == 9)
    {
        if (IsCheckpointActive()) return 0;
        if (!s_active.load()) return 0;
        std::lock_guard lock(s_mutex);
        const auto policy = s_policies.find(static_cast<uint32_t>(formId));
        return policy != s_policies.end() && policy->second.Verified && policy->second.Until > Now() ? policy->second.State : 0;
    }
    if (command == 6) return s_active.load() && !IsCheckpointActive() ? 1 : -1;
    if (IsCheckpointFrozen()) return -1;
    if (!s_active.load()) return 1; // Normal offline SFF behavior.
    if (!formId || command < 0 || (command > 5 && command != 7 && command != 8)) return -1;
    const auto action = (command == 8 ? CampaignAction::FollowerSeenWaiting : (command == 7 ? CampaignAction::FollowerSeen : static_cast<CampaignAction>(static_cast<uint8_t>(CampaignAction::FollowerClaim) + command)));
    const auto actor = static_cast<uint32_t>(formId); // Preserve all 32 bits, never pass FormIDs as floats.
    {
        std::lock_guard lock(s_mutex);
        const auto it = s_followers.find(actor);
        if (it != s_followers.end() && it->second.Until > Now())
        {
            if (it->second.Action == action) return it->second.Answer;
            if (it->second.Answer == 0) return 0;
        }
        for (auto old = s_followers.begin(); old != s_followers.end();)
            if (old->second.Until <= Now()) old = s_followers.erase(old); else ++old;
        if (s_followers.size() >= 128) return -1;
        s_followers[actor] = {action, Now() + 5000, 0};
    }
    World::Get().GetRunner().Trigger(CampaignFollowerEvent{actor, action});
    return 0;
}
int32_t CampaignService::NextFollowerPolicy() noexcept
{
    std::lock_guard lock(s_mutex);
    if (!s_active.load() || IsCheckpointActive()) return 0;
    while (!s_policyQueue.empty())
    {
        const uint32_t actor = s_policyQueue.front(); s_policyQueue.pop_front();
        const auto policy = s_policies.find(actor);
        if (policy == s_policies.end()) continue;
        policy->second.Queued = false;
        if (policy->second.Verified && policy->second.Until > Now()) return static_cast<int32_t>(actor);
    }
    return 0;
}
void CampaignService::OnFollowerPolicy(const NotifyCampaignFollower& message) noexcept
{
    if (IsCheckpointActive() || !m_ready || !m_transport.IsConnected() || !message.OwnershipEpoch || !message.Sequence || message.Policy < 1 || message.Policy > 3) return;
    const uint32_t actor = m_world.GetModSystem().GetGameId(message.Actor);
    if (!actor) return;
    // Policies are only for a local simulator at this exact epoch. Handoff
    // messages may still be queued, so defer verification to the main update.
    std::lock_guard lock(s_mutex);
    const auto old = s_policies.find(actor);
    if (old != s_policies.end() && old->second.Sequence >= message.Sequence) return;
    if (old == s_policies.end() && s_policies.size() >= 128) return;
    auto& policy = s_policies[actor];
    policy.Epoch = message.OwnershipEpoch; policy.Sequence = message.Sequence;
    policy.Verified = false; policy.State = message.Policy; policy.Until = Now() + 6000;
    policy.NextDelivery = 0;
}
void CampaignService::OnFollower(const CampaignFollowerEvent& event) noexcept
{
    if (!m_ready || !m_transport.IsConnected() || m_followerPending.size() >= 32) return;
    GameId actor;
    if (!m_world.GetModSystem().GetServerModId(event.FormId, actor) || actor.ModId == 0xffffffffu) return;
    CampaignActionRequest request;
    request.RequestId = ++m_sequence;
    request.Actor = actor; request.Action = event.Action;
    for (auto old = m_followerPending.begin(); old != m_followerPending.end();)
        if (old->second.FormId == event.FormId) old = m_followerPending.erase(old); else ++old;
    m_followerPending[request.RequestId] = {event.FormId, event.Action, Now() + 10000};
    m_transport.Send(request);
}
void CampaignService::Send(CampaignAction action, const GameId& actor)
{
    CampaignActionRequest request;
    request.RequestId = ++m_sequence;
    request.Action = action; request.Actor = actor;
    if (action == CampaignAction::Join) { request.Credential = m_credential; request.SaveProof = m_saveProof; }
    m_pending = request.RequestId;
    m_transport.Send(request);
}
void CampaignService::OnConnected(const ConnectedEvent& event) noexcept
{
    // Published only after admission; do not begin another attach recursively.
    if (IsConfigured() && !m_ready) BeginAttach(event.PlayerId);
}
void CampaignService::OnDisconnected(const DisconnectedEvent&) noexcept
{
    s_admitted.store(false); m_attachPending = false; m_attachDeadline = 0;
    s_active.store(false); m_ready = false; m_pending = 0; m_actor = {}; m_hadMenu = false;
    m_followerPending.clear();
    std::lock_guard lock(s_mutex); s_followers.clear(); s_policies.clear(); s_policyQueue.clear(); s_actor = 0; s_until = s_nextRequest = 0;
}
void CampaignService::OnInteraction(const CampaignInteractionEvent& event) noexcept
{
    if (!m_ready || !m_transport.IsConnected()) return;
    GameId actor;
    if (!m_world.GetModSystem().GetServerModId(event.FormId, actor) || actor.ModId == 0xffffffffu) return;
    m_pendingForm = event.FormId; m_replay = event.ReplayActivation;
    m_actor = actor;
    Send(CampaignAction::Acquire, actor);
}
void CampaignService::OnNotify(const NotifyCampaignAction& notify) noexcept
{
    if (!m_transport.IsConnected() || !IsConfigured()) return;
    if (notify.Action == CampaignAction::SessionState)
    {
        if (IsCheckpointActive()) return;
        if (m_ready && m_saveSetHead && !m_saveSetHead(m_saveSnapshot.Generation, notify.Epoch.c_str(), notify.Checkpoint.c_str(), notify.Revision))
            m_transport.Close();
        return;
    }
    if (notify.Action == CampaignAction::SessionExpired)
    {
        s_admitted.store(false);
        m_ready = false; m_followerPending.clear();
        { std::lock_guard lock(s_mutex); s_followers.clear(); s_policies.clear(); s_policyQueue.clear(); s_actor = 0; s_until = 0; }
        spdlog::warn("Campaign session expired; reload the enrolled checkpoint before reconnecting");
        m_transport.Close();
        return;
    }
    if (notify.Action >= CampaignAction::FollowerClaim)
    {
        const auto pending = m_followerPending.find(notify.RequestId);
        if (pending == m_followerPending.end() || pending->second.Action != notify.Action) return;
        GameId actor;
        if (!m_world.GetModSystem().GetServerModId(pending->second.FormId, actor) || actor != notify.Actor) return;
        { std::lock_guard lock(s_mutex);
          s_followers[pending->second.FormId] = {notify.Action, Now() + 2000, notify.Allowed ? 1 : -1}; }
        m_followerPending.erase(pending);
        return;
    }
    if (notify.RequestId != m_pending) return;
    if (notify.Action == CampaignAction::Join)
    {
        CampaignSave::Snapshot current;
        m_ready = !s_offlineDirty.load() && notify.Enabled && notify.Allowed && m_saveRead && m_saveRead(&current, sizeof(current))
            && current.Status == CampaignSave::Ready && current.Generation == m_saveSnapshot.Generation
            && m_saveSetHead && m_saveSetHead(current.Generation, notify.Epoch.c_str(), notify.Checkpoint.c_str(), notify.Revision);
        if (m_ready)
        {
            m_usedGeneration = current.Generation; m_attachDeadline = 0;
            s_admitted.store(true);
            m_transport.PublishCampaignConnection(m_attachPlayer);
        }
        else m_transport.Close();
        spdlog::info("Experimental campaign attach {}", m_ready ? "accepted" : "denied; NPC interactions remain blocked");
        return;
    }
    if (notify.Actor != m_actor) return;
    if (notify.Action == CampaignAction::Release) return;
    if (!notify.Allowed)
    {
        std::lock_guard lock(s_mutex); s_actor = 0; s_until = 0;
        return;
    }
    { std::lock_guard lock(s_mutex); s_actor = m_pendingForm; s_until = Now() + 18000; }
    m_nextRenew = Now() + 8000;
    if (notify.Action == CampaignAction::Acquire && m_replay)
    {
        auto* object = Cast<TESObjectREFR>(TESForm::GetById(m_pendingForm));
        auto* player = PlayerCharacter::Get();
        const auto* ui = UI::Get();
        if (!object || !player || !ui || ui->GetMenuOpen(BSFixedString("Loading Menu")) || ui->GetMenuOpen(BSFixedString("Dialogue Menu"))) return;
        const float dx = object->position.x - player->position.x;
        const float dy = object->position.y - player->position.y;
        const float dz = object->position.z - player->position.z;
        if (dx*dx + dy*dy + dz*dz > 512.f*512.f) return;
        ScopedActivateOverride activation;
        object->Activate(player, 0, nullptr, 1, 0);
    }
}
void CampaignService::OnUpdate(const UpdateEvent&) noexcept
{
    if (IsConfigured() && !m_saveRead)
    {
        if (auto* module = GetModuleHandleW(L"LoreRimCampaignCosave.dll"))
        {
            auto read = reinterpret_cast<CampaignSave::Read>(GetProcAddress(module, "LoreRimCampaign_Read"));
            auto setHead = reinterpret_cast<CampaignSave::SetHead>(GetProcAddress(module, "LoreRimCampaign_SetHead"));
            auto registration = reinterpret_cast<CampaignSave::RegisterBarrier>(GetProcAddress(module, "LoreRimCampaign_RegisterBarrier"));
            if (read && setHead && registration && registration(&CampaignService::BeforeSaveLoad)) { m_saveRead = read; m_saveSetHead = setHead; s_identityRead.store(read); }
        }
    }
    if (IsConfigured() && !IsAdmitted() && m_saveRead && Now() >= m_nextProgressCheck)
    {
        m_nextProgressCheck = Now() + 250;
        CampaignSave::Snapshot loaded;
        auto* player = PlayerCharacter::Get();
        auto* skills = player ? player->GetSkills() : nullptr;
        if (skills && m_saveRead(&loaded, sizeof(loaded)) && loaded.Status == CampaignSave::Ready)
        {
            std::array<float,38> progress{};
            progress[0] = static_cast<float>(player->GetLevel()); progress[1] = skills->xp;
            for (size_t i = 0; i < 18; ++i) { progress[2+i*2] = skills->skills[i].level; progress[3+i*2] = skills->skills[i].xp; }
            if (m_progressGeneration != loaded.Generation) { m_progressGeneration = loaded.Generation; m_progressBaseline = progress; }
            else if (progress != m_progressBaseline) NoteOfflineMutation();
        }
    }
    if (s_saveInvalidated.exchange(false))
    {
        m_ready = false; m_attachPending = false;
        if (m_transport.IsConnected()) m_transport.Close();
    }
    if (m_attachDeadline && Now() >= m_attachDeadline && !m_ready)
    {
        m_attachDeadline = 0; m_attachPending = false;
        spdlog::error("Campaign admission timed out"); m_transport.Close();
    }
    if (m_attachPending && m_proofDone.load())
    {
        m_attachPending = false;
        if (m_saveThread.joinable()) m_saveThread.join();
        CampaignSave::Snapshot current;
        if (s_offlineDirty.load() || !m_proofValid || !m_saveRead || !m_saveRead(&current, sizeof(current))
            || current.Status != CampaignSave::Ready || current.Generation != m_saveSnapshot.Generation) m_transport.Close();
        else Send(CampaignAction::Join);
    }
    {
        std::lock_guard lock(s_mutex);
        const uint64_t now = Now();
        for (auto policy = s_policies.begin(); policy != s_policies.end();)
        {
            if (policy->second.Until <= now) { policy = s_policies.erase(policy); continue; }
            bool local = false;
            auto actors = m_world.view<FormIdComponent, LocalComponent>();
            for (auto entity : actors)
                if (actors.get<FormIdComponent>(entity).Id == policy->first && actors.get<LocalComponent>(entity).OwnershipEpoch == policy->second.Epoch)
                { local = true; break; }
            policy->second.Verified = local;
            if (local && !policy->second.Queued && policy->second.NextDelivery <= now && s_policyQueue.size() < 128)
            {
                s_policyQueue.push_back(policy->first); policy->second.Queued = true;
                policy->second.NextDelivery = now + 2000;
            }
            if (!local) policy->second.Until = 0;
            ++policy;
        }
    }
    for (auto old = m_followerPending.begin(); old != m_followerPending.end();)
        if (old->second.Until <= Now()) old = m_followerPending.erase(old); else ++old;
    if (!m_ready || !m_transport.IsConnected() || !m_actor) return;
    const auto* manager = MenuTopicManager::Get();
    const auto* ui = UI::Get();
    const bool dialogue = manager && manager->menuOpen;
    const bool service = ui && (ui->GetMenuOpen(BSFixedString("BarterMenu"))
        || ui->GetMenuOpen(BSFixedString("ContainerMenu")) || ui->GetMenuOpen(BSFixedString("GiftMenu"))
        || ui->GetMenuOpen(BSFixedString("Training Menu")) || ui->GetMenuOpen(BSFixedString("CustomMenu")));
    const bool open = dialogue || service;
    if (open)
    {
        auto* speaker = dialogue ? TESObjectREFR::GetByHandle(manager->speaker.handle.iBits) : nullptr;
        if (dialogue && (!speaker || speaker->formID != m_pendingForm)) return;
        m_hadMenu = true;
        if (Now() >= m_nextRenew)
        {
            m_nextRenew = Now() + 8000;
            m_replay = false;
            Send(CampaignAction::Renew, m_actor);
        }
    }
    else if (m_hadMenu)
    {
        Send(CampaignAction::Release, m_actor);
        m_hadMenu = false;
        m_actor = {};
        std::lock_guard lock(s_mutex); s_actor = 0; s_until = 0;
    }
}

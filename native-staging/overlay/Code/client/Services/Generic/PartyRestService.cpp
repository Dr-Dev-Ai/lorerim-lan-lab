#include <Services/PartyRestService.h>
#include <Services/CalendarService.h>
#include <World.h>
#include <Events/PartyRestCommandEvent.h>
#include <Events/UpdateEvent.h>
#include <Events/DisconnectedEvent.h>
#include <Messages/PartyRestRequest.h>
#include <Messages/NotifyPartyRest.h>
#include <Games/Skyrim/Interface/UI.h>
#include <PlayerCharacter.h>
#include <AI/AIProcess.h>
#include <Misc/MiddleProcess.h>
#include <Effects/ActiveEffect.h>
#include <TimeManager.h>
#include <cmath>

std::mutex PartyRestService::s_displayMutex;
Vector<uint32_t> PartyRestService::s_displayQueue;
std::atomic<uint8_t> PartyRestService::s_pendingBenefit{0};
std::atomic<float> PartyRestService::s_pendingHours{0.f};
std::atomic<bool> PartyRestService::s_isLeader{false};
std::atomic<bool> PartyRestService::s_connected{false};

PartyRestService::PartyRestService(World& aWorld, entt::dispatcher& aDispatcher, TransportService& aTransport)
    : m_world(aWorld), m_transport(aTransport)
{
    m_commandConnection = aDispatcher.sink<PartyRestCommandEvent>().connect<&PartyRestService::OnCommand>(this);
    m_notifyConnection = aDispatcher.sink<NotifyPartyRest>().connect<&PartyRestService::OnNotify>(this);
    m_updateConnection = aDispatcher.sink<UpdateEvent>().connect<&PartyRestService::OnUpdate>(this);
    m_disconnectConnection = aDispatcher.sink<DisconnectedEvent>().connect<&PartyRestService::OnDisconnected>(this);
}
float PartyRestService::Exchange(float aCommand) noexcept
{
    if (aCommand == -7.f)
        return static_cast<float>(s_pendingBenefit.exchange(0));
    if (aCommand == -6.f)
        return s_connected.load() ? 1.f : 0.f;
    if (aCommand == -3.f)
        return s_isLeader.load() ? 1.f : 0.f;
    if (aCommand == 0.f)
        return s_pendingHours.exchange(0.f);
    if (std::isfinite(aCommand))
        World::Get().GetRunner().Trigger(PartyRestCommandEvent{aCommand});
    return 0.f;
}
void PartyRestService::Send(uint8_t aAction, float aHours, uint8_t aBenefit) noexcept
{
    PartyRestRequest request;
    request.Session = m_session;
    request.Action = static_cast<PartyRestAction>(aAction);
    request.Hours = aHours;
    request.Benefit = aBenefit;
    m_transport.Send(request);
}
void PartyRestService::OnCommand(const PartyRestCommandEvent& acEvent) noexcept
{
    if (acEvent.Command == -5.f)
    {
        UI::HideDialogueMenu();
        return;
    }
    if (acEvent.Command == -4.f)
    {
        m_pendingStatsMenu = true;
        return;
    }
    if (!m_transport.IsConnected() || !m_world.GetPartyService().IsLeader())
        return;
    if (acEvent.Command >= 1.f && acEvent.Command <= 24.f)
    {
        CaptureTimedEffects();
        m_localRest = true;
        Send(static_cast<uint8_t>(PartyRestAction::Begin), acEvent.Command);
    }
    else if (m_session && acEvent.Command >= -13.f && acEvent.Command <= -10.f)
        Send(static_cast<uint8_t>(PartyRestAction::Finish), 0.f, static_cast<uint8_t>(-acEvent.Command - 10.f));
    else if (m_session && acEvent.Command == -1.f)
        Send(static_cast<uint8_t>(PartyRestAction::Finish));
    else if (m_session && acEvent.Command == -2.f)
        Send(static_cast<uint8_t>(PartyRestAction::Cancel));
}
void PartyRestService::OnNotify(const NotifyPartyRest& acMessage) noexcept
{
    if (!m_transport.IsConnected() || !m_world.GetPartyService().IsInParty() || !acMessage.Session)
        return;
    if (acMessage.Action == PartyRestAction::Begin && acMessage.Session > m_lastReceipt)
    {
        if (!m_localRest)
            CaptureTimedEffects();
        m_session = acMessage.Session;
        m_nextReport = 0;
    }
    else if (acMessage.Action == PartyRestAction::Cancel && acMessage.Session == m_session)
    {
        m_session = 0;
        m_localRest = false;
        m_timedEffects.clear();
    }
    else if (acMessage.Action == PartyRestAction::Complete && acMessage.Session == m_session
        && acMessage.Session > m_lastReceipt && std::isfinite(acMessage.Hours) && acMessage.Hours >= 1.f && acMessage.Hours <= 24.f)
    {
        if (acMessage.AdvanceTime)
        {
            m_world.ctx().at<CalendarService>().ApplyRestElapsed(acMessage.Hours);
            ApplyTimedEffects(acMessage.Hours);
        }
        m_localRest = false;
        m_timedEffects.clear();
        // A second sleep cannot silently replace unapplied effects.
        s_pendingBenefit.store(acMessage.Benefit <= 3 ? acMessage.Benefit : 0);
        s_pendingHours.fetch_add(acMessage.Hours);
        m_lastReceipt = acMessage.Session;
        m_session = 0;
    }
}
void PartyRestService::OnUpdate(const UpdateEvent&) noexcept
{
    RefreshEquipmentDisplays();
    if (m_pendingStatsMenu)
    {
        const PlayerCharacter* pPlayer = PlayerCharacter::Get();
        const UI* pUI = UI::Get();
        if (pPlayer && pUI && !pPlayer->IsDead() && !pPlayer->IsInCombat()
            && !pUI->GetMenuOpen(BSFixedString("Loading Menu"))
            && !pUI->GetMenuOpen(BSFixedString("Dialogue Menu"))
            && !pUI->GetMenuOpen(BSFixedString("CustomMenu"))
            && !pUI->GetMenuOpen(BSFixedString("LevelUp Menu")))
        {
            m_pendingStatsMenu = !UI::ShowStatsMenu();
        }
    }
    s_connected.store(m_transport.IsConnected());
    s_isLeader.store(m_transport.IsConnected() && m_world.GetPartyService().IsLeader());
    if (!m_world.GetPartyService().IsInParty())
        s_pendingHours.store(0.f);
    if (!m_session || !m_transport.IsConnected())
        return;
    if (!m_world.GetPartyService().IsInParty())
    {
        m_session = 0;
        return;
    }
    const uint64_t cNow = m_world.GetTick();
    if (cNow < m_nextReport)
        return;
    m_nextReport = cNow + 500;
    const PlayerCharacter* pPlayer = PlayerCharacter::Get();
    const UI* pUI = UI::Get();
    const bool cSafe = pPlayer && pUI && !pPlayer->IsDead() && !pPlayer->IsInCombat()
        && !pUI->GetMenuOpen(BSFixedString("Loading Menu"))
        && !pUI->GetMenuOpen(BSFixedString("Dialogue Menu"));
    Send(static_cast<uint8_t>(cSafe ? PartyRestAction::Ready : PartyRestAction::Unsafe));
}
void PartyRestService::OnDisconnected(const DisconnectedEvent&) noexcept
{
    m_session = m_lastReceipt = m_nextReport = 0;
    m_pendingStatsMenu = false;
    m_displayInventories.clear();
    {
        std::lock_guard<std::mutex> lock(s_displayMutex);
        s_displayQueue.clear();
    }
    m_localRest = false;
    m_timedEffects.clear();
    s_pendingHours.store(0.f);
    s_pendingBenefit.store(0);
    s_isLeader.store(false);
    s_connected.store(false);
}

void PartyRestService::CaptureTimedEffects() noexcept
{
    m_timedEffects.clear();
    m_restTimeScale = TimeData::Get()->TimeScale->f;
    m_world.ctx().at<CalendarService>().BeginRestBookkeeping();
    const PlayerCharacter* pPlayer = PlayerCharacter::Get();
    const auto* pProcess = pPlayer && pPlayer->currentProcess ? pPlayer->currentProcess->middleProcess : nullptr;
    if (!pProcess || !pProcess->ActiveEffects)
        return;
    for (const ActiveEffect* pEffect : *pProcess->ActiveEffects)
    {
        if (pEffect && std::isfinite(pEffect->fDuration) && std::isfinite(pEffect->fElapsedSeconds)
            && pEffect->fDuration > 0.f && pEffect->fElapsedSeconds >= 0.f)
            m_timedEffects.push_back({pEffect, pEffect->usUniqueID, pEffect->fElapsedSeconds});
    }
}

void PartyRestService::ApplyTimedEffects(float aHours) noexcept
{
    if (!std::isfinite(m_restTimeScale) || m_restTimeScale <= 0.f)
        return;
    const float cSeconds = aHours * 3600.f / m_restTimeScale;
    const PlayerCharacter* pPlayer = PlayerCharacter::Get();
    const auto* pProcess = pPlayer && pPlayer->currentProcess ? pPlayer->currentProcess->middleProcess : nullptr;
    if (!pProcess || !pProcess->ActiveEffects)
        return;
    for (ActiveEffect* pEffect : *pProcess->ActiveEffects)
    {
        if (!pEffect || !std::isfinite(pEffect->fDuration) || pEffect->fDuration <= 0.f)
            continue;
        for (const auto& snapshot : m_timedEffects)
        {
            if (snapshot.pEffect != pEffect || snapshot.UniqueId != pEffect->usUniqueID)
                continue;
            // Native sleep may already have aged this effect. Never age it twice.
            // The normal effect update expires it; no blanket dispel or stat edits.
            const float cTarget = std::min(snapshot.Elapsed + cSeconds, pEffect->fDuration);
            if (std::isfinite(pEffect->fElapsedSeconds) && pEffect->fElapsedSeconds < cTarget)
                pEffect->fElapsedSeconds = cTarget;
            break;
        }
    }
}


int32_t PartyRestService::NextEquipmentActor() noexcept
{
    std::lock_guard<std::mutex> lock(s_displayMutex);
    if (s_displayQueue.empty())
        return 0;
    const uint32_t cId = s_displayQueue.back();
    s_displayQueue.pop_back();
    // Integer VM values preserve all 32 bits of temporary FFxxxxxx form IDs.
    return static_cast<int32_t>(cId);
}

void PartyRestService::RefreshEquipmentDisplays() noexcept
{
    if (!m_transport.IsConnected() || m_world.GetTick() < m_nextEquipmentRefresh)
        return;
    m_nextEquipmentRefresh = m_world.GetTick() + 2000;
    auto view = m_world.view<PlayerComponent, RemoteComponent, FormIdComponent>();
    for (const auto entity : view)
    {
        const uint32_t cId = view.get<FormIdComponent>(entity).Id;
        Actor* pActor = Cast<Actor>(TESForm::GetById(cId));
        if (!pActor)
            continue;
        Inventory inventory = pActor->GetInventory();
        const auto it = m_displayInventories.find(cId);
        if (it != m_displayInventories.end() && it->second == inventory)
            continue;
        m_displayInventories[cId] = std::move(inventory);
        std::lock_guard<std::mutex> lock(s_displayMutex);
        if (std::find(s_displayQueue.begin(), s_displayQueue.end(), cId) == s_displayQueue.end())
            s_displayQueue.push_back(cId);
    }
}

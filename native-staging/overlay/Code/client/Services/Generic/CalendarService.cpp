#include <Services/CalendarService.h>
#include <Services/CampaignService.h>

#include <Events/DisconnectedEvent.h>
#include <Events/UpdateEvent.h>
#include <Messages/ServerTimeSettings.h>
#include <World.h>

#include <Forms/TESObjectCELL.h>
#include <PlayerCharacter.h>
#include <TimeManager.h>

constexpr float kTransitionSpeed = 5.f;

bool CalendarService::s_gameClockLocked = false;

bool CalendarService::AllowGameTick() noexcept
{
    return !s_gameClockLocked;
}

CalendarService::CalendarService(World& aWorld, entt::dispatcher& aDispatcher, TransportService& aTransport)
    : m_world(aWorld), m_transport(aTransport)
{
    m_timeUpdateConnection = aDispatcher.sink<ServerTimeSettings>().connect<&CalendarService::OnTimeUpdate>(this);
    m_updateConnection = aDispatcher.sink<UpdateEvent>().connect<&CalendarService::HandleUpdate>(this);
    m_disconnectedConnection = aDispatcher.sink<DisconnectedEvent>().connect<&CalendarService::OnDisconnected>(this);
}

void CalendarService::OnTimeUpdate(const ServerTimeSettings& acMessage) noexcept
{
    // disable the game clock
    if (!s_gameClockLocked)
        ToggleGameClock(false);
    m_onlineTime.m_timeModel.TimeScale = acMessage.timeModel.TimeScale;
    m_onlineTime.m_timeModel.Time = acMessage.timeModel.Time;
    if (CampaignService::IsCheckpointFrozen())
    {
        auto* time = TimeData::Get();
        time->GameHour->f = acMessage.timeModel.Time;
        time->TimeScale->f = acMessage.timeModel.TimeScale;
        if (m_world.GetServerSettings().SyncPlayerCalendar)
        {
            time->GameDay->f = acMessage.timeModel.Day;
            time->GameMonth->f = acMessage.timeModel.Month;
            time->GameYear->f = acMessage.timeModel.Year;
        }
    }

    if (m_world.GetServerSettings().SyncPlayerCalendar)
    {
        m_onlineTime.m_timeModel.Day = acMessage.timeModel.Day;
        m_onlineTime.m_timeModel.Month = acMessage.timeModel.Month;
        m_onlineTime.m_timeModel.Year = acMessage.timeModel.Year;
    }
    else if (!m_lastTick)
    {
        m_onlineTime.m_timeModel.Day = m_offlineTime.m_timeModel.Day;
        m_onlineTime.m_timeModel.Month = m_offlineTime.m_timeModel.Month;
        m_onlineTime.m_timeModel.Year = m_offlineTime.m_timeModel.Year;
    }
}

void CalendarService::OnDisconnected(const DisconnectedEvent&) noexcept
{
    // signal a time transition
    m_fadeTimer = 0.f;
    ToggleGameClock(true);
    m_lastTick = 0;
    m_restSnapshotValid = false;
}

float CalendarService::TimeInterpolate(const TimeModel& aFrom, TimeModel& aTo) const
{
    const auto t = aTo.Time - aFrom.Time;
    if (t < 0.f)
    {
        const auto v = t + 24.f;
        // interpolate on the time difference, not the time
        const auto x = TiltedPhoques::Lerp(0.f, v, m_fadeTimer / kTransitionSpeed) + aFrom.Time;

        return TiltedPhoques::Mod(x, 24.f);
    }

    return TiltedPhoques::Lerp(aFrom.Time, aTo.Time, m_fadeTimer / kTransitionSpeed);
}

void CalendarService::ToggleGameClock(bool aEnable)
{
    auto* pGameTime = TimeData::Get();
    m_offlineTime.m_timeModel.Day = pGameTime->GameDay->f;
    m_offlineTime.m_timeModel.Month = pGameTime->GameMonth->f;
    m_offlineTime.m_timeModel.Year = pGameTime->GameYear->f;
    m_offlineTime.m_timeModel.Time = pGameTime->GameHour->f;
    m_offlineTime.m_timeModel.TimeScale = pGameTime->TimeScale->f;

    s_gameClockLocked = !aEnable;
}

void CalendarService::HandleUpdate(const UpdateEvent& aEvent) noexcept
{
    if (s_gameClockLocked)
    {
        const auto updateDelta = static_cast<float>(aEvent.Delta);
        auto* pGameTime = TimeData::Get();

        if (!m_lastTick)
            m_lastTick = m_world.GetTick();

        const auto now = m_world.GetTick();

        // we got disconnected or the client got ahead of us
        if (now < m_lastTick)
            return;

        const auto delta = CampaignService::IsCheckpointFrozen() ? uint64_t{0} : now - m_lastTick;
        m_lastTick = now;

        m_onlineTime.Update(delta);
        pGameTime->TimeScale->f = m_onlineTime.m_timeModel.TimeScale;
        pGameTime->GameDay->f = m_onlineTime.m_timeModel.Day;
        pGameTime->GameMonth->f = m_onlineTime.m_timeModel.Month;
        pGameTime->GameYear->f = m_onlineTime.m_timeModel.Year;
        pGameTime->GameDaysPassed->f += m_onlineTime.GetDeltaTime(delta) * (1.f / 24.f);

        // time transition in
        if (!CampaignService::IsCheckpointFrozen() && m_fadeTimer < kTransitionSpeed)
        {
            pGameTime->GameHour->f = TimeInterpolate(m_offlineTime.m_timeModel, m_onlineTime.m_timeModel);
            m_fadeTimer += updateDelta;
        }
        else
            pGameTime->GameHour->f = m_onlineTime.m_timeModel.Time;
    }
}

void CalendarService::ApplyRestElapsed(float aHours) noexcept
{
    // The preceding server time packet supplies the new hour and optionally date.
    // Local saves keep their own date when calendar synchronization is disabled.
    if (!m_world.GetServerSettings().SyncPlayerCalendar)
    {
        DateTime localDate = m_onlineTime;
        // Advance from the pre-skip hour, already replaced by the time packet.
        localDate.m_timeModel.Time = TiltedPhoques::Mod(m_onlineTime.m_timeModel.Time - aHours + 24.f, 24.f);
        localDate.AdvanceRestHours(aHours);
        m_onlineTime.m_timeModel.Day = localDate.m_timeModel.Day;
        m_onlineTime.m_timeModel.Month = localDate.m_timeModel.Month;
        m_onlineTime.m_timeModel.Year = localDate.m_timeModel.Year;
    }
    auto* pDaysPassed = TimeData::Get()->GameDaysPassed;
    const float cTarget = m_restSnapshotValid ? m_restStartDaysPassed + aHours / 24.f : pDaysPassed->f + aHours / 24.f;
    pDaysPassed->f = std::max(pDaysPassed->f, cTarget);
    m_restSnapshotValid = false;
}

void CalendarService::BeginRestBookkeeping() noexcept
{
    m_restStartDaysPassed = TimeData::Get()->GameDaysPassed->f;
    m_restSnapshotValid = true;
}

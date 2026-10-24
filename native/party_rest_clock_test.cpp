// Standalone regression using the actual upstream DateTime implementation.
#include <common/DateTime.h>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <limits>

int main()
{
    unsigned cases = 0;
    for (float scale : {0.f, 1.f, 10.f, 20.f, 1000.f})
    {
        for (unsigned month = 0; month < 12; ++month)
        {
            for (unsigned day = 1; day <= DateTime::GetNumberOfDaysByMonthIndex(month); ++day)
            {
                for (unsigned hours = 1; hours <= 24; ++hours)
                {
                    TimeModel model;
                    model.Year = 4;
                    model.Month = month;
                    model.Day = day;
                    model.Time = 23.5f;
                    model.TimeScale = scale;
                    DateTime time(model);
                    float before = time.GetTimeInDays();
                    assert(time.AdvanceRestHours(static_cast<float>(hours)));
                    assert(time.m_timeModel.TimeScale == scale);
                    assert(time.m_timeModel.Time >= 0.f && time.m_timeModel.Time < 24.f);
                    assert(time.m_timeModel.Month < 12);
                    assert(time.m_timeModel.Day >= 1);
                    assert(time.m_timeModel.Day <= DateTime::GetNumberOfDaysByMonthIndex(time.m_timeModel.Month));
                    assert(std::abs((time.GetTimeInDays() - before) * 24.f - hours) < 0.01f);
                    ++cases;
                }
            }
        }
    }

    TimeModel model;
    model.Year = 4; model.Month = 11; model.Day = 31; model.Time = 23.f;
    DateTime time(model);
    assert(time.AdvanceRestHours(8.f));
    assert(time.m_timeModel.Year == 5 && time.m_timeModel.Month == 0 && time.m_timeModel.Day == 1);
    assert(std::abs(time.m_timeModel.Time - 7.f) < 0.0001f);

    DateTime unchanged(model);
    for (float bad : {-1.f, 0.f, 25.f, std::numeric_limits<float>::infinity(),
                      std::numeric_limits<float>::quiet_NaN()})
    {
        assert(!unchanged.AdvanceRestHours(bad));
        assert(unchanged.m_timeModel == model);
        ++cases;
    }
    std::printf("PASS: %u calendar/time-scale cases plus year rollover.\n", cases);
}

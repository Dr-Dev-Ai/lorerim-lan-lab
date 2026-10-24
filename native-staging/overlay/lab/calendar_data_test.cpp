#include <DateTime.h>
#include <cassert>
#include <cmath>
#include <iostream>
#include <limits>

int main()
{
    unsigned checks = 0;
    for (float scale : {0.f, 1.f, 10.f, 20.f, 1000.f})
        for (unsigned month = 0; month < 12; ++month)
            for (unsigned day = 1; day <= DateTime::GetNumberOfDaysByMonthIndex(month); ++day)
                for (unsigned hours = 1; hours <= 24; ++hours)
                {
                    TimeModel initial;
                    initial.Year = 201;
                    initial.Month = month;
                    initial.Day = day;
                    initial.Time = 23.f;
                    initial.TimeScale = scale;
                    DateTime actual(initial);
                    assert(actual.AdvanceRestHours(static_cast<float>(hours)));
                    unsigned expectedDay = day + (23 + hours) / 24;
                    unsigned expectedMonth = month;
                    unsigned expectedYear = 201;
                    if (expectedDay > DateTime::GetNumberOfDaysByMonthIndex(month))
                    {
                        expectedDay = 1;
                        if (++expectedMonth == 12)
                        {
                            expectedMonth = 0;
                            ++expectedYear;
                        }
                    }
                    assert(std::abs(actual.m_timeModel.Time - (23 + hours) % 24) < 0.0001f);
                    assert(actual.m_timeModel.Day == expectedDay);
                    assert(actual.m_timeModel.Month == expectedMonth);
                    assert(actual.m_timeModel.Year == expectedYear);
                    assert(actual.m_timeModel.TimeScale == scale);
                    ++checks;
                }
    for (float hours : {0.f, -1.f, 25.f, std::numeric_limits<float>::infinity(), std::numeric_limits<float>::quiet_NaN()})
    {
        DateTime actual;
        const TimeModel before = actual.m_timeModel;
        assert(!actual.AdvanceRestHours(hours));
        assert(actual.m_timeModel == before);
        ++checks;
    }
    std::cout << "PASS: " << checks << " calendar cases\n";
}

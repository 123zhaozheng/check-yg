# Research: Chinese Holiday Calendar Libraries

- **Query**: How to programmatically determine if a date is a rest day (休息日) in China; available Python libraries and data sources
- **Scope**: External
- **Date**: 2026-06-05

## Findings

### Option 1: chinesecalendar (RECOMMENDED)

| Attribute | Value |
|---|---|
| Package name | `chinesecalendar` |
| Repository | https://github.com/LKI/chinese-calendar |
| PyPI | https://pypi.org/project/chinesecalendar/ |
| License | MIT |
| Stars | 1,323 |
| Latest version | 1.11.0 (2025-11-04) |
| Python support | >=3.8 (via wheel; v1.9.0+ dropped 3.7 testing but wheels still install on 3.8) |
| Data coverage | 2004 through 2026 (including 2020 Spring Festival extension) |
| Dependencies | None (pure Python, data embedded) |
| Update cadence | Annual, typically November, after State Council announcement |

**API summary:**

```python
import datetime
from chinese_calendar import is_workday, is_holiday, is_in_lieu, get_holiday_detail

date = datetime.date(2024, 5, 1)

is_workday(date)          # False - not a workday
is_holiday(date)          # True  - is a holiday
is_in_lieu(date)          # True/False - is a compensatory rest day (调休)
on_holiday, name = get_holiday_detail(date)  # (True, "Labour Day")

# Range functions
from chinese_calendar import get_holidays, get_workdays, find_workday
holidays = get_holidays(start, end, include_weekends=True)
workdays = get_workdays(start, end, include_weekends=True)
next_wd = find_workday(delta_days=1)  # next workday from today
```

**Key detail on "rest day" semantics:**
- `is_holiday(date)` returns True for any non-workday: weekends, statutory holidays, and compensatory rest days
- `is_workday(date)` returns True for regular weekdays AND adjusted workdays (调休上班的周末)
- `is_in_lieu(date)` specifically checks if a date is a compensatory rest day (the "off" side of a swap)

**Pros:**
- Most established and widely used (1,323 stars, 20 contributors)
- Zero dependencies -- data is hardcoded in `constants.py`
- Simple, clear API with exactly the functions needed
- Covers 2004-2026, includes edge cases like 2020 Spring Festival extension
- Wheel available, installs cleanly on Python 3.8
- The `constants.py` file can be extracted/translated for non-Python use

**Cons:**
- Updates only once per year (November); if State Council is late, next-year data may be unavailable temporarily
- Raises `NotImplementedError` for years outside supported range
- Does not include lunar calendar conversion (purely solar/gregorian holiday data)

---

### Option 2: holidays (vacanza/holidays)

| Attribute | Value |
|---|---|
| Package name | `holidays` |
| Repository | https://github.com/vacanza/holidays |
| PyPI | https://pypi.org/project/holidays/ |
| License | MIT |
| Stars | 2,000+ |
| Latest version | 0.97 (2026-05-18) |
| Python support (latest) | >=3.10 |
| Python support (v0.49) | >=3.8 |
| Data coverage | China: 2002-2026 |

**API summary:**

```python
import holidays
cn_holidays = holidays.China(years=range(2024, 2027))
datetime.date(2024, 10, 1) in cn_holidays  # True
cn_holidays.get(datetime.date(2024, 10, 1))  # "National Day"
```

**Pros:**
- Worldwide coverage (250+ countries) if multi-region needed
- Active development, frequent releases
- Includes China with compensatory workday/holiday data

**Cons:**
- Latest version requires Python >=3.10 (incompatible with project's Python 3.8)
- Would need to pin to v0.49 or earlier for 3.8 compatibility
- Heavier dependency (~1.4 MB wheel) for a single-country use case
- API is holiday-centric; checking "is this a workday" requires more logic than chinesecalendar
- The `HALF_DAY` category for China is niche and may not be needed

---

### Option 3: workalendar

| Attribute | Value |
|---|---|
| Package name | `workalendar` |
| Repository | https://github.com/workalendar/workalendar |
| License | MIT |
| Stars | 945 |
| China coverage | 2018-2023 only (incomplete, needs manual updates) |

**Cons:**
- China calendar data is incomplete and out of date (stops at 2023)
- Requires manual configuration to add new years
- Issues filed requesting 2024 data show the maintainer hasn't updated
- Not recommended for this use case

---

### Option 4: chinese-days (Homalos/chinese-days)

| Attribute | Value |
|---|---|
| Package name | `chinese-days` |
| Repository | https://github.com/Homalos/chinese-days |
| Stars | 3 |
| Latest version | 0.0.2 (2025-11-04) |
| Data coverage | 2004-2026 |

**Pros:**
- More granular API: holiday type enumeration, `is_weekend()` separately
- Accepts multiple date formats (str, int, datetime, date)

**Cons:**
- Very new, tiny community (3 stars, 1 contributor, v0.0.2)
- Based on vsme/chinese-days data (another small project)
- Higher risk of abandonment or bugs

---

### Option 5: NateScarlet/holiday-cn (JSON data source)

| Attribute | Value |
|---|---|
| Repository | https://github.com/NateScarlet/holiday-cn |
| Stars | 1,881 |
| Format | JSON |
| Update method | CI auto-crawls gov.cn daily |

**JSON schema:**

```json
{
  "year": 2026,
  "papers": ["https://www.gov.cn/zhengce/content/202511/content_7047090.htm"],
  "days": [
    { "name": "元旦", "date": "2026-01-01", "isOffDay": true },
    { "name": "春节", "date": "2026-02-15", "isOffDay": true },
    { "name": "春节调休", "date": "2026-02-14", "isOffDay": false }
  ]
}
```

**Pros:**
- Machine-readable JSON, language-agnostic
- Auto-updated via CI
- `isOffDay: false` entries are adjusted workdays (weekend work days)
- Can be fetched at runtime: `https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/{year}.json`

**Cons:**
- Requires network access at runtime (or vendoring the JSON)
- Needs custom parsing code; no Python helper library
- Risk of GitHub raw URL rate limiting

---

### Option 6: cnworkdays

| Attribute | Value |
|---|---|
| Package name | `cnworkdays` |
| PyPI | https://pypi.org/project/cnworkdays/ |
| Latest version | 2026.0 |
| Data coverage | 2018-2026 |

**Pros:**
- Includes `holiparse` tool to parse official State Council announcements
- Focused on working-day arithmetic (add N business days)

**Cons:**
- Very small user base
- Less intuitive for simple "is this date a rest day?" queries

---

### Official Data Source

China's State Council (国务院) publishes holiday arrangements annually, usually in October/November. The official source URLs follow this pattern:

- 2026: https://www.gov.cn/zhengce/content/202511/content_7047090.htm
- 2025: published Nov 2024
- 2024: published Oct 2023

These announcements define:
1. Which days are holidays (放假)
2. Which weekend days become workdays (调休上班)
3. Which days are compensatory rest (调休放假)

The seven statutory holidays are: New Year (元旦), Spring Festival (春节), Tomb-Sweeping Day (清明节), Labour Day (劳动节), Dragon Boat Festival (端午节), Mid-Autumn Festival (中秋节), National Day (国庆节).

---

## Recommendation

**Use `chinesecalendar`** for this project. Reasons:

1. **Python 3.8 compatible** -- project constraint met via wheel installation
2. **Zero dependencies** -- no transitive dependency risk; data is embedded
3. **Simplest API** -- `is_workday(date)` and `is_holiday(date)` are exactly what is needed
4. **Covers 2004-2026** -- more than sufficient for the 2024-2026 range
5. **Most established** -- 1,323 stars, 20 contributors, actively maintained since 2017
6. **MIT license** -- no licensing concerns

If future years are needed before the library updates (e.g., 2027 data not yet released), the fallback is to raise `NotImplementedError` gracefully or vendor the `constants.py` with manual additions based on the State Council announcement.

## Caveats / Not Found

- No library provides real-time holiday data without either a dependency update or network fetch
- `chinesecalendar` raises `NotImplementedError` for out-of-range years; calling code must handle this
- The distinction between "weekend" and "statutory holiday" vs. "compensatory rest" (调休) is handled by `is_in_lieu()` in chinesecalendar, but the simple `is_holiday()` treats all non-workdays uniformly
- No internal project code currently references any holiday/calendar library (grep confirmed)

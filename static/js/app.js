const WEEK_OPTIONS_COUNT = 52;

let currentScheduleData = null;
let teacherDirectory = {};

const LESSON_TYPE_COLOR_MAP = {
    "Лекция": "#56d6b2",
    "Практика": "#67b3ff",
    "Лабораторная": "#ce7cff",
    "Экзамен": "#ff6ca8",
    "Зачёт": "#ffd76c",
    "Зачет": "#ffd76c",
    "Консультация": "#55f0db",
    "Другое": "#ffa85c",
};

const FIXED_DAY_ORDER = [
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
];

function fillWeekSelect() {
    updateWeekBanner(getInitialWeek());
}

function getInitialWeek() {
    return 1;
}

function loadGroups() {
    $.get("/api/groups", (data) => {
        const select = $("#group-select");
        select.empty();

        data.forEach((group) => {
            select.append(`<option value="${group.id}">${group.name}</option>`);
        });

        updateInfoCardHeader();
        updatePdfLink();
    });
}

function loadTeachers() {
    $.get("/api/teachers", (data) => {
        const select = $("#teacher-select");
        select.empty();
        teacherDirectory = {};

        if (!data || data.length === 0) {
            select.append('<option value="">Преподаватели не найдены</option>');
            return;
        }

        data.forEach((teacher) => {
            teacherDirectory[teacher.name] = teacher;
            select.append(`<option value="${teacher.name}">${teacher.name}</option>`);
        });

        updatePdfLink();
    });
}

function loadCurrentWeek() {
    $.get("/api/current-week", (data) => {
        let week = data && data.week ? data.week : 1;

        if (week < 1 || week > WEEK_OPTIONS_COUNT) {
            week = 1;
        }

        currentScheduleData = currentScheduleData || {};
        currentScheduleData.week = week;

        updateWeekBanner(week);
        updatePdfLink();
        loadSchedule();
    });
}

function getCurrentWeekValue() {
    return currentScheduleData && currentScheduleData.week ? currentScheduleData.week : 1;
}

function updateWeekBanner(weekValue) {
    $("#banner-week-number").text(`${weekValue} неделя`);
}

function setTeacherCardStyle(isTeacherMode) {
    $("#info-card").toggleClass("teacher-mode", isTeacherMode);
}

function updateInfoCardHeader(data = null) {
    const mode = $("#mode").val();
    const isTeacherMode = mode === "teacher";

    setTeacherCardStyle(isTeacherMode);

    if (mode === "group") {
        $("#staff-profile-btn").addClass("hidden").attr("href", "#");

        const selectedGroupName = $("#group-select option:selected").text() || "6413-100503D";

        $("#info-entity-title").text(selectedGroupName);
        $("#info-program").text(
            data?.meta?.program || "10.05.03 Информационная безопасность автоматизированных систем",
        );
        $("#info-form").text(
            data?.meta?.education_form || "Специалист (Очная форма обучения)",
        );
        $("#info-start").text(
            `Начало учебного года: ${data?.meta?.study_year_start || "01.09.2025"}`,
        );

        return;
    }

    const teacherName = $("#teacher-select option:selected").text() || "Преподаватель";
    const teacherData = teacherDirectory[teacherName] || {};
    const staffUrl = data?.meta?.staff_url || teacherData.staff_url || "";

    $("#info-entity-title").text(teacherName);
    $("#info-program").text(
        data?.meta?.subtitle || "Преподаватель Самарского университета",
    );
    $("#info-form").text("");
    $("#info-start").text(
        `Начало учебного года: ${data?.meta?.study_year_start || "01.09.2025"}`,
    );

    if (staffUrl) {
        $("#staff-profile-btn").removeClass("hidden").attr("href", staffUrl);
    } else {
        $("#staff-profile-btn").addClass("hidden").attr("href", "#");
    }
}

function updateModeUI() {
    const mode = $("#mode").val();

    $("#group-block").toggleClass("hidden", mode !== "group");
    $("#teacher-block").toggleClass("hidden", mode !== "teacher");

    updateInfoCardHeader();
    updatePdfLink();
}

function updatePdfLink() {
    const mode = $("#mode").val();
    const week = getCurrentWeekValue();

    if (mode === "group") {
        const groupId = $("#group-select").val() || "";
        $("#download-pdf-btn").attr(
            "href",
            `/download/pdf?mode=group&group_id=${encodeURIComponent(groupId)}&week=${encodeURIComponent(week)}`,
        );
        return;
    }

    const teacherName = $("#teacher-select").val() || "";
    $("#download-pdf-btn").attr(
        "href",
        `/download/pdf?mode=teacher&name=${encodeURIComponent(teacherName)}&week=${encodeURIComponent(week)}`,
    );
}

function getSelectedSearchValue() {
    return ($("#search-input").val() || "").trim().toLowerCase();
}

function filterLessons(lessons) {
    const query = getSelectedSearchValue();

    if (!query) {
        return lessons;
    }

    return lessons.filter((lesson) => {
        const haystack = [
            lesson.title || "",
            lesson.teacher || "",
            lesson.room || "",
            lesson.group || "",
            (lesson.groups || []).join(" "),
        ]
            .join(" ")
            .toLowerCase();

        return haystack.includes(query);
    });
}

function getLessonColor(type) {
    return LESSON_TYPE_COLOR_MAP[type] || "#55e3ff";
}

function renderLessonBox(lesson, mode) {
    const type = lesson.type || "Другое";
    const color = getLessonColor(type);

    const roomHtml = lesson.room
        ? `<div class="lesson-room"><strong>Аудитория:</strong> ${lesson.room}</div>`
        : "";

    const teacherHtml = lesson.teacher
        ? `<div class="lesson-teacher"><strong>Преподаватель:</strong> ${lesson.teacher}</div>`
        : "";

    const groupHtml = mode === "teacher" && lesson.group
        ? `<div class="lesson-group"><strong>Группа:</strong> ${lesson.group}</div>`
        : "";

    const subgroupHtml = lesson.groups && lesson.groups.length
        ? `<div class="lesson-subgroups"><strong>Группы:</strong> ${lesson.groups.join(", ")}</div>`
        : "";

    return `
        <div class="lesson-box" style="--lesson-color: ${color}">
            <div class="lesson-type-badge">${type.toUpperCase()}</div>
            <div class="lesson-title">${lesson.title || "Без названия"}</div>
            ${roomHtml}
            ${teacherHtml}
            ${groupHtml}
            ${subgroupHtml}
        </div>
    `;
}

function normalizeScheduleData(data) {
    const dayMap = {};
    const timeSet = new Set();

    FIXED_DAY_ORDER.forEach((dayName) => {
        dayMap[dayName] = {
            date: "",
            lessonsByTime: {},
        };
    });

    (data.days || []).forEach((day) => {
        const dayName = day.day_name;

        if (!dayMap[dayName]) {
            dayMap[dayName] = {
                date: day.date || "",
                lessonsByTime: {},
            };
        }

        dayMap[dayName].date = day.date || "";

        filterLessons(day.lessons || []).forEach((lesson) => {
            const time = lesson.time || "Время не указано";
            timeSet.add(time);

            if (!dayMap[dayName].lessonsByTime[time]) {
                dayMap[dayName].lessonsByTime[time] = [];
            }

            dayMap[dayName].lessonsByTime[time].push(lesson);
        });
    });

    const orderedTimes = Array.from(timeSet).sort((a, b) => {
        const aStart = a.split(" - ")[0];
        const bStart = b.split(" - ")[0];
        return aStart.localeCompare(bStart);
    });

    return { dayMap, orderedTimes };
}

function renderEmptyState(message) {
    $("#schedule-container").html(`
        <div class="schedule-empty">
            ${message}
        </div>
    `);
}

function renderScheduleTable(data) {
    if (!data || !data.days || data.days.length === 0) {
        renderEmptyState(data?.message || "На выбранную неделю занятий нет.");
        return;
    }

    const { dayMap, orderedTimes } = normalizeScheduleData(data);

    if (orderedTimes.length === 0) {
        renderEmptyState(data?.message || "На выбранную неделю занятий нет.");
        return;
    }

    let html = '<div class="schedule-table-shell"><div class="schedule-table">';

    html += '<div class="schedule-head-cell time-header">Время</div>';

    FIXED_DAY_ORDER.forEach((dayName) => {
        const date = dayMap[dayName]?.date || "";
        html += `
            <div class="schedule-head-cell">
                <div class="day-name">${dayName}</div>
                <div class="day-date">${date}</div>
            </div>
        `;
    });

    orderedTimes.forEach((time) => {
        html += `<div class="schedule-time-cell">${time.replace(" - ", "<br>")}</div>`;

        FIXED_DAY_ORDER.forEach((dayName) => {
            const lessons = dayMap[dayName]?.lessonsByTime[time] || [];
            const lessonsHtml = lessons.length
                ? lessons.map((lesson) => renderLessonBox(lesson, data.mode)).join("")
                : "";

            html += `<div class="schedule-day-cell">${lessonsHtml}</div>`;
        });
    });

    html += "</div></div>";
    $("#schedule-container").html(html);
}

function renderSchedule(data) {
    currentScheduleData = data;

    updateWeekBanner(data.week || getCurrentWeekValue());
    updateInfoCardHeader(data);
    updatePdfLink();

    if (data.message && (!data.days || data.days.length === 0)) {
        renderEmptyState(data.message);
        return;
    }

    renderScheduleTable(data);
}

function loadSchedule() {
    const mode = $("#mode").val();
    const week = getCurrentWeekValue();

    updatePdfLink();
    $("#loader").removeClass("hidden");
    $("#error-message").addClass("hidden").text("");
    $("#schedule-container").empty();

    if (mode === "group") {
        const groupId = $("#group-select").val();

        $.get(`/api/schedule/group/${groupId}?week=${week}`)
            .done((data) => {
                renderSchedule(data);
            })
            .fail(() => {
                $("#error-message").removeClass("hidden").text("Ошибка загрузки расписания по группе.");
                renderEmptyState("Не удалось загрузить расписание.");
            })
            .always(() => {
                $("#loader").addClass("hidden");
            });

        return;
    }

    const teacherName = $("#teacher-select").val();

    $.get(`/api/schedule/teacher?name=${encodeURIComponent(teacherName)}&week=${week}`)
        .done((data) => {
            renderSchedule(data);
        })
        .fail(() => {
            $("#error-message").removeClass("hidden").text("Ошибка загрузки расписания по преподавателю.");
            renderEmptyState("Не удалось загрузить расписание.");
        })
        .always(() => {
            $("#loader").addClass("hidden");
        });
}

function shiftWeek(delta) {
    let current = getCurrentWeekValue() + delta;

    if (current < 1) {
        current = 1;
    }

    if (current > WEEK_OPTIONS_COUNT) {
        current = WEEK_OPTIONS_COUNT;
    }

    currentScheduleData = currentScheduleData || {};
    currentScheduleData.week = current;

    updateWeekBanner(current);
    updatePdfLink();
    loadSchedule();
}

$(document).ready(() => {
    fillWeekSelect();
    loadGroups();
    loadTeachers();
    updateModeUI();

    $("#mode").on("change", () => {
        updateModeUI();
        loadSchedule();
    });

    $("#group-select").on("change", () => {
        updateModeUI();
        updatePdfLink();
        loadSchedule();
    });

    $("#teacher-select").on("change", () => {
        updateModeUI();
        updatePdfLink();
        loadSchedule();
    });

    $("#search-input").on("input", () => {
        if (currentScheduleData) {
            renderSchedule(currentScheduleData);
        }
    });

    $("#week-prev-banner").on("click", () => {
        shiftWeek(-1);
    });

    $("#week-next-banner").on("click", () => {
        shiftWeek(1);
    });

    loadCurrentWeek();
});
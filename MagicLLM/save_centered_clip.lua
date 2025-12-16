-- save_centered_clip.lua
-- 作用：录制中按下热键（建议 Backspace），在“按下时刻后等 post_sec 秒”
--       调用 Replay Buffer 保存，从而获得 [pre_sec 秒前 ~ post_sec 秒后] 的居中片段。
-- 需要：OBS 设置中启用 Replay Buffer，最大回放时间 >= pre_sec + post_sec

local obs = obslua

-- ======== [可配默认值] 如需固定写死，可改这里，也可在脚本面板调整 ========
local pre_sec            = 10       -- 按键前保存的秒数
local post_sec           = 10       -- 按键后保存的秒数（= 保存延迟）
local auto_start_rb      = true     -- 录制开始时自动启动 Replay Buffer
local auto_stop_rb       = true     -- 录制停止时自动停止 Replay Buffer
local only_if_recording  = true     -- 仅在“正在录制”时响应热键
local debug_log          = false    -- 打开后在“脚本日志”输出调试信息
-- ==========================================================================

local hotkey_id = obs.OBS_INVALID_HOTKEY_ID
local save_pending = false
local function log(msg) if debug_log then obs.script_log(obs.LOG_INFO, "[CenteredClip] "..msg) end end

-- 一次性定时回调：到点即保存回放并移除计时器
local function save_replay_once()
    obs.timer_remove(save_replay_once)

    if not obs.obs_frontend_replay_buffer_active() then
        log("Replay Buffer 未激活，无法保存。")
        save_pending = false
        return
    end

    obs.obs_frontend_replay_buffer_save()
    log("已请求保存回放（目标片段长度=" .. tostring(pre_sec + post_sec) .. "s）")
    save_pending = false
end

-- 热键回调
local function on_hotkey(pressed)
    if not pressed then return end

    if only_if_recording and not obs.obs_frontend_recording_active() then
        log("未在录制，忽略热键。")
        return
    end

    if not obs.obs_frontend_replay_buffer_active() then
        -- 若此时才启动回放缓存，就捕不到“前 N 秒”
        -- 脚本会尽量启动，但请务必让回放缓存在录制开始时就处于运行状态
        log("Replay Buffer 未运行，尝试启动…")
        obs.obs_frontend_replay_buffer_start()
        if not obs.obs_frontend_replay_buffer_active() then
            log("启动 Replay Buffer 失败，检查设置。")
            return
        end
        log("已启动 Replay Buffer，但本次可能无法覆盖按键前的片段。")
    end

    if save_pending then
        log("已有一次保存计时在进行，忽略重复按键。")
        return
    end

    -- 关键点：延迟 post_sec 秒再保存，使回放缓冲中包含“按键后的 post_sec 秒”
    save_pending = true
    obs.timer_add(save_replay_once, post_sec * 1000)
    log("已开始保存计时（延迟 " .. tostring(post_sec) .. "s）。请确保回放缓存长度 >= " .. tostring(pre_sec + post_sec) .. "s。")
end

-- 前端事件：录制开始/结束时自动管理 Replay Buffer
local function on_event(event)
    if event == obs.OBS_FRONTEND_EVENT_RECORDING_STARTED then
        if auto_start_rb and not obs.obs_frontend_replay_buffer_active() then
            log("录制开始，自动启动 Replay Buffer。")
            obs.obs_frontend_replay_buffer_start()
        end
    elseif event == obs.OBS_FRONTEND_EVENT_RECORDING_STOPPED then
        if auto_stop_rb and obs.obs_frontend_replay_buffer_active() then
            log("录制停止，自动停止 Replay Buffer。")
            obs.obs_frontend_replay_buffer_stop()
        end
    end
end

-- =============== OBS 脚本接口（属性/更新/加载/保存/描述） ===============
function script_description()
    return [[
按下 Backspace（或你绑定的热键）后，延迟 post 秒保存回放，从而得到：
[按键前 pre 秒  +  按键后 post 秒] 的居中片段（默认 10s + 10s）。

使用须知：
1) 设置 → 输出 → 回放缓存：启用，最大回放时间 ≥ pre+post（建议 20s）。
2) 设置 → 热键：为 “保存 20s 片段（Backspace）” 绑定按键（建议 Backspace）。
3) 录制开始后，回放缓存需保持运行（脚本可自动管理）。
]]
end

function script_properties()
    local props = obs.obs_properties_create()
    obs.obs_properties_add_int(props, "pre_sec",  "按键前保存秒数", 0, 300, 1)
    obs.obs_properties_add_int(props, "post_sec", "按键后保存秒数（保存延迟）", 0, 300, 1)
    obs.obs_properties_add_bool(props, "auto_start_rb",     "录制开始时自动启动回放缓存")
    obs.obs_properties_add_bool(props, "auto_stop_rb",      "录制结束时自动停止回放缓存")
    obs.obs_properties_add_bool(props, "only_if_recording", "仅在录制时响应热键")
    obs.obs_properties_add_bool(props, "debug_log",         "输出调试日志到脚本日志")
    return props
end

function script_defaults(settings)
    obs.obs_data_set_default_int(settings,  "pre_sec",          10)
    obs.obs_data_set_default_int(settings,  "post_sec",         10)
    obs.obs_data_set_default_bool(settings, "auto_start_rb",    true)
    obs.obs_data_set_default_bool(settings, "auto_stop_rb",     true)
    obs.obs_data_set_default_bool(settings, "only_if_recording",true)
    obs.obs_data_set_default_bool(settings, "debug_log",        false)
end

function script_update(settings)
    pre_sec           = obs.obs_data_get_int(settings,  "pre_sec")
    post_sec          = obs.obs_data_get_int(settings,  "post_sec")
    auto_start_rb     = obs.obs_data_get_bool(settings, "auto_start_rb")
    auto_stop_rb      = obs.obs_data_get_bool(settings, "auto_stop_rb")
    only_if_recording = obs.obs_data_get_bool(settings, "only_if_recording")
    debug_log         = obs.obs_data_get_bool(settings, "debug_log")
end

function script_load(settings)
    -- 注册热键（在 设置→热键 里绑定具体按键，比如 Backspace）
    hotkey_id = obs.obs_hotkey_register_frontend("save_centered_clip_hotkey",
                    "保存 20s 片段（Backspace）", on_hotkey)
    local a = obs.obs_data_get_array(settings, "save_centered_clip_hotkey")
    obs.obs_hotkey_load(hotkey_id, a)
    obs.obs_data_array_release(a)

    obs.obs_frontend_add_event_callback(on_event)

    -- 若脚本加载时已经在录制且启用了自动管理，确保回放缓存已启动
    if obs.obs_frontend_recording_active() and auto_start_rb and not obs.obs_frontend_replay_buffer_active() then
        obs.obs_frontend_replay_buffer_start()
    end
end

function script_save(settings)
    local a = obs.obs_hotkey_save(hotkey_id)
    obs.obs_data_set_array(settings, "save_centered_clip_hotkey", a)
    obs.obs_data_array_release(a)
end

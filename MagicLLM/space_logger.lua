obs = obslua

local hotkey_id = obs.OBS_INVALID_HOTKEY_ID
local log_path = ""
-- 新增：根据操作系统选择换行符（Windows -> \r\n，其它 -> \n）
local newline = (package.config:sub(1,1) == '\\') and '\r\n' or '\n'

function script_description()
  return "按下热键把当前录制/直播的输出时间写入到文本文件（自动附加日期和时间）。\n" ..
         "建议将热键绑定为空格或 Ctrl+Space。"
end

function script_properties()
  local p = obs.obs_properties_create()
  obs.obs_properties_add_path(p, "log_path", "日志文件", obs.OBS_PATH_FILE,
                              "Text Files (*.txt);;All Files (*.*)", nil)
  return p
end

function script_update(s)
  log_path = obs.obs_data_get_string(s, "log_path")
end

function script_load(s)
  hotkey_id = obs.obs_hotkey_register_frontend("space_logger_mark",
               "Space Logger: 标记", on_hotkey)
  local a = obs.obs_data_get_array(s, "space_logger_mark")
  obs.obs_hotkey_load(hotkey_id, a); obs.obs_data_array_release(a)
end

function script_save(s)
  local a = obs.obs_hotkey_save(hotkey_id)
  obs.obs_data_set_array(s, "space_logger_mark", a)
  obs.obs_data_array_release(a)
end

local function get_output_time_s()
  -- 优先取录制输出；没有则取直播输出
  local out = obs.obs_frontend_get_recording_output()
  if out == nil then out = obs.obs_frontend_get_streaming_output() end
  if out ~= nil then
    local frames = obs.obs_output_get_total_frames(out)
    obs.obs_output_release(out)
    local fps = obs.obs_get_active_fps()
    if fps > 0 then return frames / fps end
  end
  return nil
end

local function write_mark()
  if log_path == nil or log_path == "" then
    obs.script_log(obs.LOG_WARNING, "未设置日志文件路径"); return
  end
  local t = get_output_time_s()
  if t == nil then
    obs.script_log(obs.LOG_WARNING, "没有活动的录制或直播输出"); return
  end
  local h = math.floor(t / 3600)
  local m = math.floor((t % 3600) / 60)
  local s = math.floor(t % 60)
  local ms = math.floor((t - math.floor(t)) * 1000)
  local ts = string.format("%02d:%02d:%02d.%03d", h, m, s, ms)
  local prefix = os.date("[%Y-%m-%d %H:%M:%S] ")
  local f = io.open(log_path, "a")
  if f then
    f:write(prefix .. ts .. newline)
    f:close()
    obs.script_log(obs.LOG_INFO, "Mark: "..ts)
  else
    obs.script_log(obs.LOG_ERROR, "无法打开日志文件: "..log_path)
  end
end

function on_hotkey(pressed)
  if pressed then write_mark() end
end

-- mGBA <-> Python bridge for the vision agent.
-- Configured as an autorun script in mGBA settings (Settings > Scripting).
--
-- Line protocol on TCP :8888 —
--   press <button> <hold_frames>   hold a button, release, then reply "ok"
--   shot <abs_path>                save a screenshot, reply "ok"
--   ping                           reply "pong"
-- One command in flight at a time; every reply ends with "\n".
-- Every handler is defensive: a client that connects and vanishes (port
-- scanners, health checks) must never crash the script, or mGBA halts it
-- and the bridge dies with it.

-- Per-instance port so two mGBA+agent pairs can run side by side; the agent
-- sets this env var when it launches mGBA. Manual launches default to 8888.
local PORT = tonumber(os.getenv("POKEMON_BRIDGE_PORT") or "") or 8888

-- GB and GBA share these key indices (GBA adds R=8/L=9, unused here).
local KEYS = {
  a = 0, b = 1, select = 2, start = 3,
  right = 4, left = 5, up = 6, down = 7,
}

local sock = nil
local hold = nil  -- {key=<int>, frames_left=<int>} while a press is active

local function reply(msg)
  if not sock then return end
  local ok = pcall(function() sock:send(msg .. "\n") end)
  if not ok then sock = nil end
end

local function handle(line)
  local cmd, rest = line:match("^(%S+)%s*(.*)$")
  if cmd == "ping" then
    reply("pong")
  elseif cmd == "shot" then
    if emu == nil then
      reply("err no game loaded")
      return
    end
    local ok = pcall(function() emu:screenshot(rest) end)
    reply(ok and "ok" or "err screenshot failed")
  elseif cmd == "press" then
    if emu == nil then
      reply("err no game loaded")
      return
    end
    local name, frames = rest:match("^(%S+)%s+(%d+)$")
    local key = name and KEYS[name:lower()]
    if key then
      emu:addKey(key)
      hold = { key = key, frames_left = tonumber(frames) }
      -- "ok" is sent by the frame callback once the button is released.
    else
      reply("err unknown button")
    end
  else
    reply("err unknown command")
  end
end

callbacks:add("frame", function()
  if hold and emu then
    hold.frames_left = hold.frames_left - 1
    if hold.frames_left <= 0 then
      emu:clearKey(hold.key)
      hold = nil
      reply("ok")
    end
  end
end)

local buffer = ""
local function onReceived()
  if not sock then return end
  while true do
    local chunk, err = nil, nil
    local ok = pcall(function() chunk, err = sock:receive(1024) end)
    if not ok then
      sock = nil
      return
    end
    if not chunk then
      if err ~= socket.ERRORS.AGAIN then
        pcall(function() sock:close() end)
        sock = nil
      end
      return
    end
    buffer = buffer .. chunk
    while true do
      local line, remainder = buffer:match("^([^\n]*)\n(.*)$")
      if not line then break end
      buffer = remainder
      pcall(handle, line)
    end
  end
end

local server = socket.bind(nil, PORT)
if not server then
  console:error("bridge: could not bind port " .. PORT)
  return
end
server:add("received", function()
  local ok, client = pcall(function() return server:accept() end)
  if not ok or not client then return end
  if sock then pcall(function() sock:close() end) end  -- newest connection wins
  sock = client
  buffer = ""
  hold = nil
  sock:add("received", onReceived)
end)
server:listen()
console:log("bridge: listening on port " .. PORT)

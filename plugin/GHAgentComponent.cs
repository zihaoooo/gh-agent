using System;
using System.Collections.Generic;
using System.Drawing;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using System.Windows.Forms;
using Grasshopper.Kernel;

namespace GHAgent
{
    public class GHAgentComponent : GH_Component
    {
        private static readonly HttpClient _http = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(3)
        };

        private const string SERVER_URL = "http://localhost:8000";
        private Timer _canvasTimer;
        private Timer _commandTimer;


        // ─────────────────────────────────────────────
        // CONSTRUCTOR
        // ─────────────────────────────────────────────

        public GHAgentComponent()
            : base(
                "GH Agent",
                "GHAgent",
                "Syncs your Grasshopper canvas with the GH Agent AI assistant.\nOpen Claude Desktop and start chatting.",
                "GH Agent",
                "Canvas")
        {
            Rhino.RhinoApp.Closing += OnRhinoClosing;

            // Canvas sync — triggers a re-solve every 5 seconds so Claude always has fresh data
            _canvasTimer = new Timer { Interval = 5000 };
            _canvasTimer.Tick += (s, e) =>
            {
                var doc = OnPingDocument();
                if (doc != null)
                    doc.ScheduleSolution(1, d => ExpireSolution(false));
            };
            _canvasTimer.Start();

            // Command polling — checks for queued commands from Claude every 2 seconds
            // OnPingDocument() must be called here on the UI thread, then passed into Task.Run.
            // Calling it from the thread pool returns null and silently kills command execution.
            _commandTimer = new Timer { Interval = 2000 };
            _commandTimer.Tick += (s, e) =>
            {
                var doc = OnPingDocument();
                if (doc == null) return;
                Task.Run(async () => await PollAndExecuteCommands(doc));
            };
            _commandTimer.Start();
        }


        // ─────────────────────────────────────────────
        // PARAMS
        // ─────────────────────────────────────────────

        protected override void RegisterInputParams(GH_InputParamManager pManager) { }

        protected override void RegisterOutputParams(GH_OutputParamManager pManager)
        {
            pManager.AddTextParameter("Status", "S", "GH Agent sync status", GH_ParamAccess.item);
        }


        // ─────────────────────────────────────────────
        // SOLVE
        // ─────────────────────────────────────────────

        protected override void SolveInstance(IGH_DataAccess DA)
        {
            var nodes = ReadCanvas();
            DA.SetData(0, $"✓ GH Agent running  |  {nodes.Count} components synced");
            Task.Run(async () => await PostCanvas(nodes));
        }


        // ─────────────────────────────────────────────
        // READ CANVAS
        // ─────────────────────────────────────────────

        private List<Dictionary<string, object>> ReadCanvas()
        {
            var nodes = new List<Dictionary<string, object>>();
            var doc = OnPingDocument();
            if (doc == null) return nodes;

            foreach (var obj in doc.Objects)
            {
                try
                {
                    if (obj.InstanceGuid == InstanceGuid) continue;

                    var errors = new List<string>();
                    if (obj is IGH_ActiveObject active)
                        foreach (var msg in active.RuntimeMessages(GH_RuntimeMessageLevel.Error))
                            errors.Add(msg);

                    nodes.Add(new Dictionary<string, object>
                    {
                        ["id"]        = obj.InstanceGuid.ToString(),
                        ["name"]      = obj.Name     ?? "",
                        ["nickname"]  = obj.NickName ?? "",
                        ["type"]      = obj.GetType().Name,
                        ["has_error"] = errors.Count > 0,
                        ["messages"]  = errors,
                        ["position"]  = new Dictionary<string, object>
                        {
                            ["x"] = (double)obj.Attributes.Pivot.X,
                            ["y"] = (double)obj.Attributes.Pivot.Y
                        }
                    });
                }
                catch { }
            }

            return nodes;
        }


        // ─────────────────────────────────────────────
        // POST CANVAS
        // ─────────────────────────────────────────────

        private async Task PostCanvas(List<Dictionary<string, object>> nodes)
        {
            try
            {
                var payload = JsonSerializer.Serialize(new { nodes });
                var content = new StringContent(payload, Encoding.UTF8, "application/json");
                await _http.PostAsync($"{SERVER_URL}/canvas", content);
            }
            catch { }
        }


        // ─────────────────────────────────────────────
        // COMMAND POLLING
        // Asks the server for pending commands every 2 seconds.
        // Runs off the main thread — execution is scheduled back onto it.
        // ─────────────────────────────────────────────

        private async Task PollAndExecuteCommands(GH_Document doc)
        {
            try
            {
                var response = await _http.GetAsync($"{SERVER_URL}/commands");
                if (!response.IsSuccessStatusCode) return;

                var json = await response.Content.ReadAsStringAsync();
                var commands = JsonSerializer.Deserialize<List<JsonElement>>(json);
                if (commands == null || commands.Count == 0) return;

                foreach (var cmd in commands)
                    ScheduleCommand(doc, cmd);
            }
            catch (Exception ex)
            {
                Rhino.RhinoApp.WriteLine($"[GHAgent] PollAndExecuteCommands error: {ex.Message}");
            }
        }

        private void ScheduleCommand(GH_Document doc, JsonElement cmd)
        {
            // All canvas operations must run on Grasshopper's main thread
            doc.ScheduleSolution(1, d =>
            {
                try
                {
                    string type      = cmd.GetProperty("type").GetString() ?? "";
                    string commandId = cmd.TryGetProperty("command_id", out var cid) ? cid.GetString() ?? "" : "";
                    string result;

                    switch (type)
                    {
                        case "add_component":
                            result = ExecuteAddComponent(d, cmd);
                            break;
                        case "set_script":
                            result = ExecuteSetScript(d, cmd);
                            break;
                        // Future command types go here — no rebuild needed for Python-side tools
                        // case "move_component":   result = ExecuteMoveComponent(d, cmd);   break;
                        // case "connect_wire":     result = ExecuteConnectWire(d, cmd);     break;
                        // case "set_value":        result = ExecuteSetValue(d, cmd);        break;
                        // case "delete_component": result = ExecuteDeleteComponent(d, cmd); break;
                        // case "select_component": result = ExecuteSelectComponent(d, cmd); break;
                        default:
                            result = $"Unknown command type: {type}";
                            break;
                    }

                    Task.Run(async () => await PostCommandResult(commandId, result));
                }
                catch (Exception ex)
                {
                    string commandId = cmd.TryGetProperty("command_id", out var cid) ? cid.GetString() ?? "" : "";
                    Task.Run(async () => await PostCommandResult(commandId, $"Error: {ex.Message}"));
                }
            });
        }


        // ─────────────────────────────────────────────
        // COMMAND: ADD COMPONENT
        // ─────────────────────────────────────────────

        /// <summary>
        /// Finds a component proxy by name and optional category.
        /// Category filtering prevents Land Kit or other plugins from shadowing
        /// native GH components that share the same name (e.g. "Area", "Move").
        /// </summary>
        private IGH_ObjectProxy FindComponentByNameAndCategory(string name, string category = null)
        {
            foreach (var proxy in Grasshopper.Instances.ComponentServer.ObjectProxies)
            {
                if (!string.Equals(proxy.Desc.Name, name, StringComparison.OrdinalIgnoreCase))
                    continue;

                if (category == null)
                    return proxy;

                if (string.Equals(proxy.Desc.Category, category, StringComparison.OrdinalIgnoreCase))
                    return proxy;
            }
            return null;
        }

        private string ExecuteAddComponent(GH_Document doc, JsonElement cmd)
        {
            string ghName      = cmd.TryGetProperty("gh_name",      out var n)   ? n.GetString()   ?? "" : "";
            string ghCategory  = cmd.TryGetProperty("gh_category",  out var cat) ? cat.GetString() ?? "" : "";
            string displayName = cmd.TryGetProperty("display_name", out var dn)  ? dn.GetString()  ?? "" : ghName;
            string nearNodeId  = cmd.TryGetProperty("near_node_id", out var nr)  ? nr.GetString()  ?? "" : "";

            if (string.IsNullOrEmpty(ghName))
                return "add_component failed: gh_name was empty.";

            // Category-aware lookup prevents other plugins (e.g. Land Kit) from shadowing
            // native GH components with matching names.
            var proxy = FindComponentByNameAndCategory(ghName, string.IsNullOrEmpty(ghCategory) ? null : ghCategory)
                     ?? FindComponentByNameAndCategory(ghName); // fallback: first name match, any category

            if (proxy == null)
            {
                Rhino.RhinoApp.WriteLine($"[GHAgent] Component not found: '{ghName}' (category: '{ghCategory}')");
                return $"Component '{ghName}' not found. It may not be installed.";
            }

            // Determine placement position
            float x = 100f, y = 100f;
            if (!string.IsNullOrEmpty(nearNodeId))
            {
                foreach (var obj in doc.Objects)
                {
                    if (obj.InstanceGuid.ToString() == nearNodeId)
                    {
                        x = obj.Attributes.Pivot.X + 220f;
                        y = obj.Attributes.Pivot.Y;
                        break;
                    }
                }
            }

            var instance = proxy.CreateInstance();
            doc.AddObject(instance, false);
            instance.Attributes.Pivot = new System.Drawing.PointF(x, y);
            instance.Attributes.ExpireLayout();
            doc.NewSolution(false);

            return $"Added '{displayName}' at ({x:F0}, {y:F0}).";
        }


        // ─────────────────────────────────────────────
        // COMMAND: SET PYTHON SCRIPT
        // Uses reflection to avoid hard-coding the RhinoCodePluginGH API.
        // ─────────────────────────────────────────────

        private string ExecuteSetScript(GH_Document doc, JsonElement cmd)
        {
            string nodeId = cmd.TryGetProperty("node_id", out var n) ? n.GetString() ?? "" : "";
            string code   = cmd.TryGetProperty("code",    out var c) ? c.GetString() ?? "" : "";

            if (string.IsNullOrEmpty(nodeId)) return "set_script failed: node_id was empty.";
            if (string.IsNullOrEmpty(code))   return "set_script failed: code was empty.";

            IGH_DocumentObject target = null;
            foreach (var obj in doc.Objects)
            {
                if (obj.InstanceGuid.ToString() == nodeId) { target = obj; break; }
            }

            if (target == null) return $"Node {nodeId} not found on canvas.";
            if (target.GetType().Name != "Python3Component")
                return $"Node is a {target.GetType().Name}, not a Python3Component.";

            // Use reflection — avoids a hard dependency on RhinoCodePluginGH.dll
            var scriptProp = target.GetType().GetProperty("Script")
                          ?? target.GetType().GetProperty("Code")
                          ?? target.GetType().GetProperty("ScriptSource");

            if (scriptProp != null && scriptProp.CanWrite)
            {
                scriptProp.SetValue(target, code);
                doc.NewSolution(false);
                return "Script written successfully.";
            }

            // Property not found or read-only — try common setter methods
            var setMethod = target.GetType().GetMethod("SetScript")
                         ?? target.GetType().GetMethod("SetCode")
                         ?? target.GetType().GetMethod("SetScriptSource");

            if (setMethod != null)
            {
                setMethod.Invoke(target, new object[] { code });
                doc.NewSolution(false);
                return "Script written successfully.";
            }

            return "Could not find a writable script property on Python3Component. The RhinoCode API may have changed.";
        }


        // ─────────────────────────────────────────────
        // POST COMMAND RESULT
        // ─────────────────────────────────────────────

        private async Task PostCommandResult(string commandId, string result)
        {
            try
            {
                var payload = JsonSerializer.Serialize(new { command_id = commandId, result });
                var content = new StringContent(payload, Encoding.UTF8, "application/json");
                await _http.PostAsync($"{SERVER_URL}/command_result", content);
            }
            catch { }
        }


        // ─────────────────────────────────────────────
        // ICON
        // ─────────────────────────────────────────────

        protected override Bitmap Icon
        {
            get
            {
                var bmp = new Bitmap(24, 24);
                using (var g = Graphics.FromImage(bmp))
                {
                    g.Clear(Color.Transparent);
                    using (var b = new SolidBrush(Color.FromArgb(26, 26, 46)))
                        g.FillRectangle(b, 0, 0, 24, 24);
                    using (var b = new SolidBrush(Color.FromArgb(76, 175, 80)))
                        g.FillRectangle(b, 2, 3, 3, 18);
                    using (var font = new Font("Arial", 7f, FontStyle.Bold))
                    using (var b = new SolidBrush(Color.White))
                        g.DrawString("GH", font, b, 6f, 7f);
                    using (var b = new SolidBrush(Color.FromArgb(76, 175, 80)))
                        g.FillEllipse(b, 17, 17, 5, 5);
                }
                return bmp;
            }
        }

        public override Guid ComponentGuid =>
            new Guid("a1b2c3d4-e5f6-7890-abcd-ef1234567890");

        public override void RemovedFromDocument(GH_Document document)
        {
            Rhino.RhinoApp.Closing -= OnRhinoClosing;
            _canvasTimer?.Stop();
            _canvasTimer?.Dispose();
            _commandTimer?.Stop();
            _commandTimer?.Dispose();
            base.RemovedFromDocument(document);
        }

        private void OnRhinoClosing(object sender, EventArgs e)
        {
            _canvasTimer?.Stop();
            _canvasTimer?.Dispose();
            _canvasTimer = null;
            _commandTimer?.Stop();
            _commandTimer?.Dispose();
            _commandTimer = null;
        }
    }
}

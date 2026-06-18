import React from "react";
import { StreamlitComponentBase, Streamlit } from "streamlit-component-lib";
import Gantt from "frappe-gantt";
import "frappe-gantt-css";
import "./gantt-theme.css";

const EMPTY_MSG_STYLE = {
  padding: "48px 24px",
  textAlign: "center",
  color: "#7a8899",
  fontFamily:
    '"DM Sans", "SF Pro Display", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif',
  fontSize: "14px",
  lineHeight: "1.6",
  letterSpacing: "0.01em",
};

const CTX_MENU_STYLE = {
  position: "fixed",
  backgroundColor: "#ffffff",
  border: "1px solid #e4e8ec",
  borderRadius: "8px",
  boxShadow:
    "0 8px 24px -4px rgba(26,35,50,0.12), 0 2px 6px -1px rgba(26,35,50,0.06)",
  zIndex: 1000,
  minWidth: "190px",
  padding: "4px 0",
  fontFamily:
    '"DM Sans", "SF Pro Display", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif',
};

class GanttComponent extends StreamlitComponentBase {
  constructor(props) {
    super(props);
    this.containerRef = React.createRef();
    this.ganttInstance = null;
    this.state = { contextMenu: null };
    this._handleDocClick = () => this.setState({ contextMenu: null });
  }

  componentDidMount() {
    // Skip super.componentDidMount() — it calls setFrameHeight() with no args,
    // which auto-detects body.scrollHeight and clips the horizontal scrollbar.
    document.addEventListener("click", this._handleDocClick);
    this._buildGantt();
  }

  componentDidUpdate(prevProps) {
    // Skip super.componentDidUpdate() — same setFrameHeight() clipping issue.
    const prev = prevProps.args || {};
    const curr = this.props.args || {};

    const tasksChanged =
      JSON.stringify(prev.tasks) !== JSON.stringify(curr.tasks);
    const depsChanged =
      JSON.stringify(prev.dependencies) !== JSON.stringify(curr.dependencies);
    const viewChanged = prev.view_mode !== curr.view_mode;

    if (tasksChanged || depsChanged || viewChanged) {
      this._buildGantt();
    } else {
      this._setFrameHeightWithScrollbar();
    }

    if (curr.today_scroll && this.ganttInstance) {
      this.ganttInstance.scroll_current();
    }

    this._applySearchHighlighting();
    this._applySelectedHighlighting();
  }

  componentWillUnmount() {
    document.removeEventListener("click", this._handleDocClick);
  }

  _setFrameHeightWithScrollbar() {
    const gc = document.querySelector(".gantt-container");
    if (gc) {
      // offsetHeight includes border + padding but NOT the horizontal scrollbar
      // rendered below the content. Add 20px buffer for the scrollbar track.
      Streamlit.setFrameHeight(gc.offsetHeight + 20);
    } else {
      Streamlit.setFrameHeight();
    }
  }

  _sendEvent(eventType, payload) {
    Streamlit.setComponentValue({ type: eventType, ...payload });
  }

  _formatTasks() {
    const { tasks = [], dependencies = [] } = this.props.args || {};
    return tasks.map((t) => {
      const taskDeps = dependencies
        .filter((d) => d.to_id === t.id)
        .map((d) => d.from_id)
        .join(", ");

      return {
        id: t.id,
        name: t.name,
        start: t.start,
        end: t.end,
        progress: t.progress || 0,
        dependencies: taskDeps,
        custom_class: t.custom_class || "",
      };
    });
  }

  _buildGantt() {
    const el = this.containerRef.current;
    const { tasks = [], view_mode = "Week" } = this.props.args || {};
    if (!el || tasks.length === 0) return;

    el.innerHTML = "";
    const ganttTasks = this._formatTasks();

    // Patch classList.add to handle space-separated tokens that Frappe
    // Gantt passes via task.custom_class (classList.add rejects spaces).
    const origAdd = DOMTokenList.prototype.add;
    DOMTokenList.prototype.add = function (...tokens) {
      const split = tokens.flatMap((t) => t.split(/\s+/).filter(Boolean));
      return origAdd.apply(this, split);
    };

    try {
      this.ganttInstance = new Gantt(el, ganttTasks, {
        view_mode: view_mode,
        bar_height: 24,
        bar_corner_radius: 4,
        padding: 16,
        column_width: view_mode === "Day" ? 32 : view_mode === "Month" ? 140 : 120,
        date_format: "YYYY-MM-DD",
        upper_header_height: 36,
        lower_header_height: 28,
        arrow_curve: 6,
        lines: "both",
        popup_on: "click",
        move_dependencies: true,
        readonly: false,
        readonly_dates: false,
        readonly_progress: true,
        today_button: false,
        view_mode_select: false,
        infinite_padding: false,
        scroll_to: "today",

        on_click: (task) => {
          this._sendEvent("click", { task_id: task.id });
        },

        on_date_change: (task, start, end) => {
          this._sendEvent("date_change", {
            task_id: task.id,
            new_start: _fmtDate(start),
            new_end: _fmtDate(end),
          });
        },

        on_after_date_change: (task, start, end) => {
          this._sendEvent("after_date_change", {
            task_id: task.id,
            new_start: _fmtDate(start),
            new_end: _fmtDate(end),
          });
        },

        on_progress_change: () => {},

        on_view_change: (mode) => {
          this._sendEvent("view_change", { mode: mode?.name || mode });
        },

        popup: ({ task, set_title, set_subtitle, set_details }) => {
          const { tasks: allTasks = [] } = this.props.args || {};
          const detail = allTasks.find((t) => t.id === task.id);

          set_title(task.id);
          set_subtitle(task.name);

          if (detail) {
            const lines = [];
            if (detail.location) lines.push(`Location: ${detail.location}`);
            lines.push(`Start: ${detail.start}`);
            lines.push(`End: ${detail.end}`);
            if (detail.status) lines.push(`Status: ${detail.status}`);
            set_details(lines.join("\n"));
          }
        },
      });
    } catch (err) {
      console.error("Gantt init error:", err);
      el.innerHTML =
        '<div style="padding:24px;color:#c9453d;font-family:sans-serif;font-size:13px">' +
        "<strong>Gantt rendering error:</strong> " +
        err.message +
        "</div>";
      Streamlit.setFrameHeight();
      return;
    } finally {
      DOMTokenList.prototype.add = origAdd;
    }

    const svgEl = el.querySelector("svg");
    if (svgEl) {
      // Bind right-click context menu
      svgEl.addEventListener("contextmenu", this._handleContext);

      // Prevent Frappe Gantt from initiating drag on right-click mousedown.
      // Without this, Frappe sets is_dragging=true and bar_being_dragged=false,
      // which causes its mouseup handler to show the popup on right-click.
      svgEl.addEventListener(
        "mousedown",
        (e) => {
          if (e.button === 2) e.stopPropagation();
        },
        true,
      );
    }

    // Bind double-click on empty space
    el.addEventListener("dblclick", this._handleDblClick);

    this._setFrameHeightWithScrollbar();
  }

  _handleContext = (e) => {
    e.preventDefault();
    const barEl = e.target.closest(".bar-wrapper");
    if (!barEl) {
      this.setState({ contextMenu: null });
      return;
    }
    const taskId = barEl.getAttribute("data-id");
    const { tasks = [] } = this.props.args || {};
    const detail = tasks.find((t) => t.id === taskId);
    if (!taskId) return;

    this.setState({
      contextMenu: {
        x: e.clientX,
        y: e.clientY,
        taskId,
        isComplete: detail?.is_complete || false,
      },
    });

    // Frappe Gantt's bar mouseup handler fires for all buttons (including
    // right-click) and shows its popup. Hide it after the mouseup cycle.
    requestAnimationFrame(() => {
      if (this.ganttInstance) this.ganttInstance.hide_popup();
    });
  };

  _handleDblClick = (e) => {
    if (e.target.closest(".bar-wrapper")) return;
    this._sendEvent("double_click_empty", { x_offset: e.offsetX });
  };

  _handleContextAction(action) {
    const taskId = this.state.contextMenu?.taskId;
    this.setState({ contextMenu: null });
    if (!taskId) return;
    this._sendEvent("context_menu", { task_id: taskId, action });
  }

  _applySearchHighlighting() {
    const el = this.containerRef.current;
    if (!el) return;
    const { search_query = "", tasks = [] } = this.props.args || {};
    const query = search_query.toLowerCase().trim();
    const bars = el.querySelectorAll(".bar-wrapper");

    bars.forEach((bar) => {
      const taskId = bar.getAttribute("data-id") || "";
      if (!query) {
        bar.style.opacity = "1";
        return;
      }
      const detail = tasks.find((t) => t.id === taskId);
      const hit =
        taskId.toLowerCase().includes(query) ||
        (detail?.name || "").toLowerCase().includes(query) ||
        (detail?.location || "").toLowerCase().includes(query);
      bar.style.opacity = hit ? "1" : "0.2";
    });

    if (query) {
      const first = Array.from(bars).find((b) => b.style.opacity === "1");
      if (first) first.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  _applySelectedHighlighting() {
    const el = this.containerRef.current;
    if (!el) return;
    const { selected_task_id } = this.props.args || {};
    el.querySelectorAll(".bar-wrapper").forEach((bar) => {
      const taskId = bar.getAttribute("data-id") || "";
      bar.classList.toggle("selected", taskId === selected_task_id);
    });
  }

  render() {
    const { tasks = [] } = this.props.args || {};
    const { contextMenu } = this.state;

    if (tasks.length === 0) {
      return (
        <div style={EMPTY_MSG_STYLE}>
          No tasks to display. Add a task to see the Gantt chart.
        </div>
      );
    }

    return (
      <div style={{ position: "relative", width: "100%" }}>
        <div
          ref={this.containerRef}
          style={{
            width: "100%",
          }}
        />

        {contextMenu && (
          <div
            style={{
              ...CTX_MENU_STYLE,
              top: contextMenu.y,
              left: contextMenu.x,
            }}
          >
            <CtxItem
              label="Edit in sidebar"
              onClick={() => this._handleContextAction("edit")}
            />
            <CtxItem
              label={
                contextMenu.isComplete ? "Mark incomplete" : "Mark complete"
              }
              onClick={() => this._handleContextAction("toggle_complete")}
            />
            <CtxItem
              label="Add child task"
              onClick={() => this._handleContextAction("add_child")}
            />
            <div
              style={{ borderTop: "1px solid #eef0f2", margin: "4px 0" }}
            />
            <CtxItem
              label="Delete task"
              onClick={() => this._handleContextAction("delete")}
              danger
            />
          </div>
        )}
      </div>
    );
  }
}

function CtxItem({ label, onClick, danger = false }) {
  const [hover, setHover] = React.useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        padding: "7px 16px",
        cursor: "pointer",
        color: danger ? "#c9453d" : "#1a2332",
        fontSize: "13px",
        fontWeight: 450,
        letterSpacing: "0.01em",
        backgroundColor: hover
          ? danger
            ? "#fef2f1"
            : "#f0f4f8"
          : "transparent",
        transition: "background-color 0.12s ease",
      }}
    >
      {label}
    </div>
  );
}

function _fmtDate(d) {
  if (!d) return null;
  const dt = d instanceof Date ? d : new Date(d);
  const y = dt.getFullYear();
  const m = String(dt.getMonth() + 1).padStart(2, "0");
  const day = String(dt.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export default GanttComponent;

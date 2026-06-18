import React from "react";
import ReactDOM from "react-dom/client";
import { withStreamlitConnection } from "streamlit-component-lib";
import GanttComponent from "./GanttComponent";

const ConnectedGantt = withStreamlitConnection(GanttComponent);

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <ConnectedGantt />
  </React.StrictMode>
);

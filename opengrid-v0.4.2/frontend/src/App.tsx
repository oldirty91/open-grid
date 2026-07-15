import MapApp from "./MapApp";
import PluginsPage from "./PluginsPage";
import ArtifactsPage from "./ArtifactsPage";

export default function App(){
  const path=window.location.pathname;
  if(path.startsWith("/plugins")) return <PluginsPage/>;
  if(path.startsWith("/artifacts")) return <ArtifactsPage/>;
  return <MapApp/>;
}

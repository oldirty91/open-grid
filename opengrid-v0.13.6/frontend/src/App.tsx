import MapApp from "./MapApp";
import PluginsPage from "./PluginsPage";
import ArtifactsPage from "./ArtifactsPage";
import EntityProfilePage from "./EntityProfilePage";

export default function App(){
  const path=window.location.pathname;
  if(path.startsWith("/plugins")) return <PluginsPage/>;
  if(path.startsWith("/artifacts")) return <ArtifactsPage/>;
  if(path.startsWith("/entities/")) return <EntityProfilePage/>;
  return <MapApp/>;
}

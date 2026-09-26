"""Local manifest plugin lifecycle; plugins never execute arbitrary code."""
import json
import shutil
from pathlib import Path
from .manifests import BUILTIN_MANIFEST, validate, validate_package, runtime_packages

class PluginRegistry:
 def __init__(self,data):self.root=Path(data)/'plugins';self.root.mkdir(parents=True,exist_ok=True)
 def install(self,manifest_path):
  manifest=validate_package(json.loads(Path(manifest_path).read_text()));plugin_id=manifest.get('id')
  if not isinstance(plugin_id,str) or not plugin_id.replace('-','').isalnum():raise ValueError('플러그인 id가 올바르지 않습니다.')
  target=self.root/(plugin_id+'.json');target.write_text(json.dumps({**manifest,'enabled':True},ensure_ascii=False));return plugin_id
 def list(self):
  return [json.loads(path.read_text()) for path in sorted(self.root.glob('*.json'))]
 def runtime_packages(self):
  """Return only reviewed, enabled declarations for a runtime turn."""
  return runtime_packages(self.list())
 def declared_packages(self):
  """Return every reviewed installed declaration for the owner settings view."""
  self.runtime_packages()  # Validate even disabled declarations before exposing them.
  return [{'id':'builtin','enabled':True,**BUILTIN_MANIFEST},*[validate(manifest) for manifest in self.list()]]
 def set_enabled(self,plugin_id,enabled):
  path=self.root/(plugin_id+'.json');manifest=validate(json.loads(path.read_text()));manifest['enabled']=bool(enabled);path.write_text(json.dumps(manifest,ensure_ascii=False));return manifest
 def remove(self,plugin_id):
  path=self.root/(plugin_id+'.json')
  if not path.exists():raise ValueError('플러그인을 찾을 수 없습니다.')
  path.unlink()

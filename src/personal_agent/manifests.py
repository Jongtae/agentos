"""Validated declarations for AgentOS roles and bounded local tools."""
import json
from pathlib import Path

HOST_ACTIONS={'web_search','public_page_read','bounded_public_research','weather','calendar_query','calendar_draft_create','calendar_draft_update','calendar_draft_cancel','list_roots','find_files','read_file','list_notes','save_note','save_memory','list_memory','list_agents','delegate_agent'}
WRITE_ACTIONS={'save_note','save_memory','delegate_agent','calendar_draft_create','calendar_draft_update','calendar_draft_cancel'}
ROLE_PERMISSIONS={'read_only','bounded_write'}

BUILTIN_MANIFEST={'version':1,'id':'builtin','tools':[{'id':name,'host_action':name,'mode':'bounded_write' if name in WRITE_ACTIONS else 'read_only'} for name in sorted(HOST_ACTIONS)],'roles':[
 {'id':'researcher','name':'조사 에이전트','instructions':'Research the assigned question using read-only tools when needed. Cite evidence and identify gaps. Never invent findings.','permissions':['read_only'],'tools':['web_search','weather','list_roots','find_files','read_file','list_notes','list_agents']},
 {'id':'reviewer','name':'검토 에이전트','instructions':'Produce a review report of the supplied material: findings, uncertainties, and concrete improvements. Review what is provided now. Do not ask whether to edit or save files; editing is not your task. Use read-only tools only if evidence is missing.','permissions':['read_only'],'tools':['web_search','weather','list_roots','find_files','read_file','list_notes','list_agents']},
 {'id':'planner','name':'계획 에이전트','instructions':'Turn the supplied goal into a concise, ordered plan. State assumptions, dependencies, risks, and what needs the owner\'s decision. Use only supplied material or read-only evidence. Never perform actions, change notes, or delegate work.','permissions':['read_only'],'tools':['web_search','weather','list_roots','find_files','read_file','list_notes']},
]}

def _id(value):return isinstance(value,str) and bool(value) and value.replace('-','').replace('_','').isalnum() and value[0].isalpha()

def validate(manifest):
 if not isinstance(manifest,dict) or manifest.get('version')!=1:raise ValueError('매니페스트 버전 1이 필요합니다.')
 if 'id' in manifest and not _id(manifest['id']):raise ValueError('플러그인 id가 올바르지 않습니다.')
 tools=manifest.get('tools',[]);roles=manifest.get('roles',[])
 if not isinstance(tools,list) or not isinstance(roles,list):raise ValueError('tools와 roles는 목록이어야 합니다.')
 tool_ids=set()
 for tool in tools:
  if not isinstance(tool,dict) or not _id(tool.get('id')) or tool['id'] in tool_ids or tool.get('host_action') not in HOST_ACTIONS:raise ValueError('허용하지 않은 도구 매니페스트입니다.')
  if tool.get('mode') != ('bounded_write' if tool['host_action'] in WRITE_ACTIONS else 'read_only'):raise ValueError('도구 모드는 host action의 안전 등급과 일치해야 합니다.')
  tool_ids.add(tool['id'])
 role_ids=set()
 for role in roles:
  permissions=role.get('permissions',[]) if isinstance(role,dict) else []
  declared_tools=role.get('tools',[]) if isinstance(role,dict) else []
  if not isinstance(role,dict) or not _id(role.get('id')) or role['id'] in role_ids or not isinstance(role.get('name',''),str) or not isinstance(role.get('instructions',''),str) or not isinstance(permissions,list) or not permissions or any(permission not in ROLE_PERMISSIONS for permission in permissions) or not isinstance(declared_tools,list) or len(set(declared_tools))!=len(declared_tools) or any(tool not in tool_ids for tool in declared_tools):raise ValueError('허용하지 않은 역할 매니페스트입니다.')
  actions={tool['host_action'] for tool in tools if tool['id'] in declared_tools}
  if 'bounded_write' not in permissions and actions & WRITE_ACTIONS:raise ValueError('읽기 전용 역할은 쓰기 도구를 선언할 수 없습니다.')
  role_ids.add(role['id'])
 return manifest

def validate_package(manifest):
 """Validate a third-party package: the built-in id is reserved (#604)."""
 manifest=validate(manifest)
 if manifest.get('id')==BUILTIN_MANIFEST['id']:raise ValueError('builtin은 AgentOS 기본 패키지 전용 id입니다.')
 return manifest

def load(path):return validate(json.loads(Path(path).read_text()))

def runtime_packages(manifests):
 """Resolve built-ins plus enabled declarations without granting new actions."""
 builtin=validate(BUILTIN_MANIFEST);packages=[{'id':'builtin','enabled':True,**builtin}];seen_tools={tool['id'] for tool in builtin['tools']};seen_roles={role['id'] for role in builtin['roles']}
 for package in manifests:
  manifest=validate_package(package)
  if manifest.get('enabled') is not True:continue
  package_id=manifest.get('id')
  if not package_id:raise ValueError('활성 플러그인에는 id가 필요합니다.')
  tools=manifest['tools'];roles=manifest['roles'];tool_ids={tool['id'] for tool in tools};role_ids={role['id'] for role in roles}
  if seen_tools & tool_ids or seen_roles & role_ids:raise ValueError('활성 패키지의 도구 또는 역할 id가 중복됩니다.')
  seen_tools|=tool_ids;seen_roles|=role_ids;packages.append({'id':package_id,'enabled':True,'tools':tools,'roles':roles})
 return packages

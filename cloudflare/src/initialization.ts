import {randomUUID, timingSafeEqual} from 'node:crypto';
import {RULES} from './core.ts';
import {canonical, digest} from './integrity.ts';

export interface InitializationCommand {
  operation:'INITIALIZE_EMPTY_ISOLATED_MOCK';
  target_object_id:string;
  request_id:string;
  operator:string;
  authorization_reference:string;
  reason:string;
}
export interface InitializationPolicy {
  MOCK_INIT_ENABLED?:string;
  MOCK_INIT_OBJECT_ID?:string;
  MOCK_INIT_TOKEN?:string;
}
export interface InitializationReceipt extends InitializationCommand {
  receipt_version:1;
  schema_version:1;
  mode:'DRY_RUN_MOCK_ONLY';
  rules_version:string;
  stock_event_model_version:'revision-market-v2';
  index_event_model_version:'indices-revision-market-v2';
  initialized_at_utc:string;
  receipt_id:string;
}

function validateCommand(command:InitializationCommand, receipt=false) {
  if (!command || command.operation !== 'INITIALIZE_EMPTY_ISOLATED_MOCK') throw Error('INITIALIZATION_COMMAND_INVALID');
  const allowed=['operation','target_object_id','request_id','operator','authorization_reference','reason',
    ...(receipt?['receipt_version','schema_version','mode','rules_version','stock_event_model_version','index_event_model_version','initialized_at_utc','receipt_id']:[])];
  if(Object.keys(command).some(key=>!allowed.includes(key)))throw Error('INITIALIZATION_COMMAND_INVALID');
  for (const key of ['target_object_id','request_id','operator','authorization_reference','reason'] as const) {
    if (typeof command[key] !== 'string' || !command[key].trim() || command[key].length > 512) throw Error('INITIALIZATION_COMMAND_INVALID');
  }
}

// Internal RPC is the boundary, never a Dashboard route. Secrets stay in the
// caller/policy; neither the receipt nor errors contain the provided credential.
export function authorizeInitialization(policy:InitializationPolicy, actualObjectId:string, command:InitializationCommand, credential:string) {
  if (policy.MOCK_INIT_ENABLED !== 'EXPLICIT_ISOLATED_MOCK_V1' || !policy.MOCK_INIT_OBJECT_ID ||
      !policy.MOCK_INIT_TOKEN || policy.MOCK_INIT_TOKEN.length < 32) throw Error('INITIALIZATION_DISABLED');
  const expected = Buffer.from(digest(policy.MOCK_INIT_TOKEN));
  const supplied = Buffer.from(digest(typeof credential === 'string' ? credential : ''));
  if (!timingSafeEqual(expected, supplied)) throw Error('INITIALIZATION_UNAUTHORIZED');
  validateCommand(command);
  if (actualObjectId !== policy.MOCK_INIT_OBJECT_ID || command.target_object_id !== actualObjectId) throw Error('INITIALIZATION_TARGET_MISMATCH');
}

export function makeReceipt(command:InitializationCommand):InitializationReceipt {
  validateCommand(command);
  return {...command, receipt_version:1, schema_version:1, mode:'DRY_RUN_MOCK_ONLY', rules_version:RULES,
    stock_event_model_version:'revision-market-v2', index_event_model_version:'indices-revision-market-v2',
    initialized_at_utc:new Date().toISOString(), receipt_id:randomUUID()};
}

export function localTestReceipt():InitializationReceipt {
  return makeReceipt({operation:'INITIALIZE_EMPTY_ISOLATED_MOCK', target_object_id:'LOCAL_SQLITE_TEST',
    request_id:randomUUID(), operator:'LOCAL_OFFLINE_HARNESS', authorization_reference:'LOCAL_TEST_ONLY',
    reason:'Explicit isolated offline test initialization'});
}

export function verifyReceipt(body:string, hash:string, auditBody:string, auditHash:string) {
  if (body === 'EXPLICIT_OFFLINE_INITIALIZATION') throw Error('STATE_ERROR: LEGACY_INITIALIZATION_MIGRATION_REQUIRED');
  if (digest(body) !== hash || digest(auditBody) !== auditHash || auditBody !== body || hash !== auditHash) throw Error('STATE_ERROR: INITIALIZATION_RECEIPT_HASH');
  const receipt = JSON.parse(body) as InitializationReceipt;
  validateCommand(receipt,true);
  if (canonical(receipt) !== body || receipt.receipt_version !== 1 || receipt.schema_version !== 1 ||
      receipt.mode !== 'DRY_RUN_MOCK_ONLY' || receipt.rules_version !== RULES ||
      receipt.stock_event_model_version !== 'revision-market-v2' || receipt.index_event_model_version !== 'indices-revision-market-v2' ||
      typeof receipt.receipt_id !== 'string' || !/^[0-9a-f-]{36}$/.test(receipt.receipt_id) ||
      typeof receipt.initialized_at_utc !== 'string' || !Number.isFinite(Date.parse(receipt.initialized_at_utc)) || !receipt.initialized_at_utc.endsWith('Z')) {
    throw Error('STATE_ERROR: INITIALIZATION_RECEIPT_SCHEMA');
  }
  return receipt;
}

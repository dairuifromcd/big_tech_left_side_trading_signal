import {createHash} from 'node:crypto';
import {sorted} from './core.ts';

export const canonical = (value:any):string => JSON.stringify(sorted(value), (_key, item) => {
  if (typeof item === 'number' && !Number.isFinite(item)) throw Error('NON_FINITE');
  return item;
});
export const digest = (value:string):string => createHash('sha256').update(value).digest('hex');

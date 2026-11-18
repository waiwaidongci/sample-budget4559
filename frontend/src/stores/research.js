import {studies,runs,joints} from '../api/research.js';
export const store={studies:[],runs:[],joints:[],studyId:0,runId:0,jointId:0,jointRunStatus:'',rows:[]};
export async function load(){[store.studies,store.runs,store.joints]=await Promise.all([studies.list(),runs.list(),joints.list()]);if(!store.studyId)store.studyId=store.studies[0]?.id||0;}
export async function loadRows(){store.rows=store.studyId?await studies.rows(store.studyId):[];}

import { DrugKeyword } from '../types';

export const DRUG_KEYWORDS: DrugKeyword[] = [
  // --- MONGOLIAN KEYWORDS ---
  // Traditional Drugs
  { id: 'mn-trad-1', word: 'хар тамхи', category: 'traditional', translation: '毒品(泛指)', language: 'mn' },
  { id: 'mn-trad-2', word: 'опиум', category: 'traditional', translation: '鸦片', language: 'mn' },
  { id: 'mn-trad-3', word: 'геройн', category: 'traditional', translation: '海洛因', language: 'mn' },
  { id: 'mn-trad-4', word: 'морфин', category: 'traditional', translation: '吗啡', language: 'mn' },
  { id: 'mn-trad-5', word: 'кодеин', category: 'traditional', translation: '可待因', language: 'mn' },
  { id: 'mn-trad-6', word: 'макны ургамал', category: 'traditional', translation: '罂粟植株', language: 'mn' },
  { id: 'mn-trad-7', word: 'макны шүүс', category: 'traditional', translation: '罂粟汁液', language: 'mn' },

  // Cannabis
  { id: 'mn-can-1', word: 'марихуана', category: 'cannabis', translation: '大麻', language: 'mn' },
  { id: 'mn-can-2', word: 'каннабис', category: 'cannabis', translation: '大麻植物', language: 'mn' },
  { id: 'mn-can-3', word: 'гашиш', category: 'cannabis', translation: '大麻脂/哈希什', language: 'mn' },
  { id: 'mn-can-4', word: 'каннабис тос', category: 'cannabis', translation: '大麻油', language: 'mn' },
  { id: 'mn-can-5', word: 'каннабис цэцэг', category: 'cannabis', translation: '大麻花', language: 'mn' },
  { id: 'mn-can-6', word: 'каннабис үр', category: 'cannabis', translation: '大麻籽', language: 'mn' },

  // Amphetamine / Synthetics
  { id: 'mn-amp-1', word: 'метамфетамин', category: 'amphetamine', translation: '冰毒/甲基苯丙胺', language: 'mn' },
  { id: 'mn-amp-2', word: 'лед', category: 'amphetamine', translation: '冰毒(俗称)', language: 'mn' },
  { id: 'mn-amp-3', word: 'амфетамин', category: 'amphetamine', translation: '安非他明', language: 'mn' },
  { id: 'mn-amp-4', word: 'МДМА', category: 'amphetamine', translation: '摇头丸/MDMA', language: 'mn' },
  { id: 'mn-amp-5', word: 'экстази', category: 'amphetamine', translation: '摇头丸', language: 'mn' },
  { id: 'mn-amp-6', word: 'фентермин', category: 'amphetamine', translation: '芬特明', language: 'mn' },
  { id: 'mn-amp-7', word: 'спид', category: 'amphetamine', translation: '速度丸', language: 'mn' },

  // CNB / Anaga (Special focus)
  { id: 'mn-cnb-1', word: 'анага бодис', category: 'cnb', translation: '安纳咖(通用名)', language: 'mn' },
  { id: 'mn-cnb-2', word: 'кофеин натри бензоат', category: 'cnb', translation: '苯甲酸钠咖啡因', language: 'mn' },
  { id: 'mn-cnb-3', word: 'КНБ', category: 'cnb', translation: '安纳咖缩写', language: 'mn' },
  { id: 'mn-cnb-4', word: 'хууль бус КНБ', category: 'cnb', translation: '非法安纳咖', language: 'mn' },
  { id: 'mn-cnb-5', word: 'кофеин хольц', category: 'cnb', translation: '含咖啡因混合管制物', language: 'mn' },

  // Cathinone
  { id: 'mn-cat-1', word: 'мефедрон', category: 'cathinone', translation: '喵喵/麻古酮', language: 'mn' },
  { id: 'mn-cat-2', word: 'метилэфедрон', category: 'cathinone', translation: '甲卡西酮', language: 'mn' },
  { id: 'mn-cat-3', word: '4-МЕС', category: 'cathinone', translation: '4-MEC', language: 'mn' },
  { id: 'mn-cat-4', word: 'катинон', category: 'cathinone', translation: '卡西酮', language: 'mn' },

  // Fentanyl
  { id: 'mn-fen-1', word: 'фентанил', category: 'fentanyl', translation: '芬太尼', language: 'mn' },
  { id: 'mn-fen-2', word: 'карфентанил', category: 'fentanyl', translation: '卡芬太尼', language: 'mn' },
  { id: 'mn-fen-3', word: 'метилфентанил', category: 'fentanyl', translation: '甲基芬太尼', language: 'mn' },
  { id: 'mn-fen-4', word: 'фуранилфентанил', category: 'fentanyl', translation: '呋喃芬太尼', language: 'mn' },

  // Hallucinogens
  { id: 'mn-hal-1', word: 'кетамин', category: 'hallucinogens', translation: '氯胺酮/K粉', language: 'mn' },
  { id: 'mn-hal-2', word: 'К-порошок', category: 'hallucinogens', translation: 'K粉(俗称)', language: 'mn' },
  { id: 'mn-hal-3', word: 'ЛСД', category: 'hallucinogens', translation: 'LSD致幻剂', language: 'mn' },
  { id: 'mn-hal-4', word: 'псилоцибин', category: 'hallucinogens', translation: '迷幻蘑菇/裸盖菇素', language: 'mn' },
  { id: 'mn-hal-5', word: 'мескалин', category: 'hallucinogens', translation: '麦司卡林', language: 'mn' },
  { id: 'mn-hal-6', word: 'ПХП', category: 'hallucinogens', translation: '苯环己哌啶(PCP)', language: 'mn' },

  // Psychotropic / Sedatives
  { id: 'mn-psy-1', word: 'триазолам', category: 'psychotropic', translation: '三唑仑', language: 'mn' },
  { id: 'mn-psy-2', word: 'флунитразепам', category: 'psychotropic', translation: '氟硝安定/蓝精灵', language: 'mn' },
  { id: 'mn-psy-3', word: 'ГХБ', category: 'psychotropic', translation: '羟基丁酸(GHB)', language: 'mn' },
  { id: 'mn-psy-4', word: 'метаквалон', category: 'psychotropic', translation: '安眠酮', language: 'mn' },

  // Precursors
  { id: 'mn-pre-1', word: 'эфедрин', category: 'precursors', translation: '麻黄碱', language: 'mn' },
  { id: 'mn-pre-2', word: 'псевдоэфедрин', category: 'precursors', translation: '伪麻黄碱', language: 'mn' },
  { id: 'mn-pre-3', word: 'ацетон', category: 'precursors', translation: '丙酮', language: 'mn' },
  { id: 'mn-pre-4', word: 'перманганат калия', category: 'precursors', translation: '高锰酸钾', language: 'mn' },

  // Actions
  { id: 'mn-act-1', word: 'хил хар тамхины наймаа', category: 'actions', translation: '跨境贩毒', language: 'mn' },
  { id: 'mn-act-2', word: 'гаалийн илрүүлэлт', category: 'actions', translation: '海关查获', language: 'mn' },
  { id: 'mn-act-3', word: 'хар тамхины хямдрал', category: 'actions', translation: '缉毒行动/打击毒品', language: 'mn' },
  { id: 'mn-act-4', word: 'хууль бус импорт', category: 'actions', translation: '非法进口', language: 'mn' },
  { id: 'mn-act-5', word: 'хар тамхи хадгалсан', category: 'actions', translation: '藏匿毒品', language: 'mn' },

  // --- ENGLISH KEYWORDS ---
  // Traditional Drugs
  { id: 'en-trad-1', word: 'opium', category: 'traditional', translation: '鸦片', language: 'en' },
  { id: 'en-trad-2', word: 'heroin', category: 'traditional', translation: '海洛因', language: 'en' },
  { id: 'en-trad-3', word: 'morphine', category: 'traditional', translation: '吗啡', language: 'en' },
  { id: 'en-trad-4', word: 'codeine', category: 'traditional', translation: '可待因', language: 'en' },
  { id: 'en-trad-5', word: 'opium poppy', category: 'traditional', translation: '罂粟', language: 'en' },

  // Cannabis
  { id: 'en-can-1', word: 'cannabis', category: 'cannabis', translation: '大麻', language: 'en' },
  { id: 'en-can-2', word: 'marijuana', category: 'cannabis', translation: '大麻(常用)', language: 'en' },
  { id: 'en-can-3', word: 'hashish', category: 'cannabis', translation: '大麻树脂', language: 'en' },
  { id: 'en-can-4', word: 'hash oil', category: 'cannabis', translation: '大麻油', language: 'en' },
  { id: 'en-can-5', word: 'cannabis flower', category: 'cannabis', translation: '大麻花', language: 'en' },

  // Amphetamine / Synthetics
  { id: 'en-amp-1', word: 'methamphetamine', category: 'amphetamine', translation: '甲基苯丙胺/冰毒', language: 'en' },
  { id: 'en-amp-2', word: 'crystal meth', category: 'amphetamine', translation: '冰毒晶体', language: 'en' },
  { id: 'en-amp-3', word: 'ice', category: 'amphetamine', translation: '冰毒(俗称)', language: 'en' },
  { id: 'en-amp-4', word: 'amphetamine', category: 'amphetamine', translation: '安非他明', language: 'en' },
  { id: 'en-amp-5', word: 'MDMA', category: 'amphetamine', translation: 'MDMA', language: 'en' },
  { id: 'en-amp-6', word: 'ecstasy', category: 'amphetamine', translation: '摇头丸', language: 'en' },

  // CNB / Anaga
  { id: 'en-cnb-1', word: 'caffeine sodium benzoate', category: 'cnb', translation: '苯甲酸钠咖啡因(安纳咖)', language: 'en' },
  { id: 'en-cnb-2', word: 'CNB', category: 'cnb', translation: '安纳咖缩写', language: 'en' },
  { id: 'en-cnb-3', word: 'anaga drug', category: 'cnb', translation: '安纳咖毒品', language: 'en' },
  { id: 'en-cnb-4', word: 'controlled caffeine stimulant', category: 'cnb', translation: '受管制的咖啡因兴奋剂', language: 'en' },
  { id: 'en-cnb-5', word: 'illegal CNB smuggling', category: 'cnb', translation: '非法安纳咖走私', language: 'en' },

  // Cathinone
  { id: 'en-cat-1', word: 'mephedrone', category: 'cathinone', translation: '喵喵/麻古酮', language: 'en' },
  { id: 'en-cat-2', word: 'methcathinone', category: 'cathinone', translation: '甲卡西酮', language: 'en' },
  { id: 'en-cat-3', word: '4-MEC', category: 'cathinone', translation: '4-MEC', language: 'en' },
  { id: 'en-cat-4', word: 'cathinone', category: 'cathinone', translation: '卡西酮', language: 'en' },

  // Fentanyl
  { id: 'en-fen-1', word: 'fentanyl', category: 'fentanyl', translation: '芬太尼', language: 'en' },
  { id: 'en-fen-2', word: 'carfentanil', category: 'fentanyl', translation: '卡芬太尼', language: 'en' },
  { id: 'en-fen-3', word: 'methylfentanyl', category: 'fentanyl', translation: '甲基芬太尼', language: 'en' },
  { id: 'en-fen-4', word: 'furanylfentanyl', category: 'fentanyl', translation: '呋喃芬太尼', language: 'en' },

  // Hallucinogens & Psychotropic
  { id: 'en-hal-1', word: 'ketamine', category: 'hallucinogens', translation: '氯胺酮', language: 'en' },
  { id: 'en-hal-2', word: 'LSD', category: 'hallucinogens', translation: 'LSD', language: 'en' },
  { id: 'en-hal-3', word: 'psilocybin', category: 'hallucinogens', translation: '裸盖菇素/迷幻蘑菇', language: 'en' },
  { id: 'en-hal-4', word: 'mescaline', category: 'hallucinogens', translation: '麦司卡林', language: 'en' },
  { id: 'en-hal-5', word: 'PCP', category: 'hallucinogens', translation: 'PCP', language: 'en' },
  { id: 'en-hal-6', word: 'GHB', category: 'hallucinogens', translation: 'GHB/神仙水', language: 'en' },

  // Actions
  { id: 'en-act-1', word: 'Mongolia drug seizure', category: 'actions', translation: '蒙古毒品查获', language: 'en' },
  { id: 'en-act-2', word: 'cross-border drug trafficking', category: 'actions', translation: '跨境毒品贩运', language: 'en' },
  { id: 'en-act-3', word: 'Mongolia customs bust', category: 'actions', translation: '蒙古海关查缉', language: 'en' },
  { id: 'en-act-4', word: 'anti-narcotics operation', category: 'actions', translation: '禁毒缉毒行动', language: 'en' },
  { id: 'en-act-5', word: 'drug precursor chemicals', category: 'actions', translation: '易制毒化学品', language: 'en' },

  // --- RUSSIAN KEYWORDS ---
  // Traditional Drugs
  { id: 'ru-trad-1', word: 'опиум', category: 'traditional', translation: '鸦片', language: 'ru' },
  { id: 'ru-trad-2', word: 'героин', category: 'traditional', translation: '海洛因', language: 'ru' },
  { id: 'ru-trad-3', word: 'морфин', category: 'traditional', translation: '吗啡', language: 'ru' },
  { id: 'ru-trad-4', word: 'кодеин', category: 'traditional', translation: '可待因', language: 'ru' },
  { id: 'ru-trad-5', word: 'мак', category: 'traditional', translation: '罂粟', language: 'ru' },

  // Cannabis
  { id: 'ru-can-1', word: 'марихуана', category: 'cannabis', translation: '大麻', language: 'ru' },
  { id: 'ru-can-2', word: 'каннабис', category: 'cannabis', translation: '大麻(官方学名)', language: 'ru' },
  { id: 'ru-can-3', word: 'гашиш', category: 'cannabis', translation: '大麻脂/哈希什', language: 'ru' },
  { id: 'ru-can-4', word: 'гашишное масло', category: 'cannabis', translation: '大麻油', language: 'ru' },

  // Amphetamine / Synthetics
  { id: 'ru-amp-1', word: 'метамфетамин', category: 'amphetamine', translation: '甲基苯丙胺/冰毒', language: 'ru' },
  { id: 'ru-amp-2', word: 'лёд', category: 'amphetamine', translation: '冰毒(俗称)', language: 'ru' },
  { id: 'ru-amp-3', word: 'амфетамин', category: 'amphetamine', translation: '安非他明', language: 'ru' },
  { id: 'ru-amp-4', word: 'МДМА', category: 'amphetamine', translation: '摇头丸/MDMA', language: 'ru' },
  { id: 'ru-amp-5', word: 'экстази', category: 'amphetamine', translation: '摇头丸', language: 'ru' },

  // CNB / Anaga
  { id: 'ru-cnb-1', word: 'кофеин-натрий бензоат', category: 'cnb', translation: '苯甲酸钠咖啡因', language: 'ru' },
  { id: 'ru-cnb-2', word: 'КНБ', category: 'cnb', translation: '安纳咖缩写', language: 'ru' },
  { id: 'ru-cnb-3', word: 'анага наркотик', category: 'cnb', translation: '安纳咖毒品', language: 'ru' },
  { id: 'ru-cnb-4', word: 'незаконный КНБ', category: 'cnb', translation: '非法安纳咖', language: 'ru' },
  { id: 'ru-cnb-5', word: 'контрабанда кофеина', category: 'cnb', translation: '咖啡因走私', language: 'ru' },

  // Cathinones & Fentanyls
  { id: 'ru-cat-1', word: 'мефедрон', category: 'cathinone', translation: '喵喵/麻古酮', language: 'ru' },
  { id: 'ru-cat-2', word: 'метилэфедрон', category: 'cathinone', translation: '甲卡西酮', language: 'ru' },
  { id: 'ru-cat-3', word: 'фентанил', category: 'fentanyl', translation: '芬太尼', language: 'ru' },
  { id: 'ru-cat-4', word: 'карфентанил', category: 'fentanyl', translation: '卡芬太尼', language: 'ru' },

  // Psychotropics & Hallucinogens
  { id: 'ru-hal-1', word: 'кетамин', category: 'hallucinogens', translation: '氯胺酮', language: 'ru' },
  { id: 'ru-hal-2', word: 'ЛСД', category: 'hallucinogens', translation: 'LSD', language: 'ru' },
  { id: 'ru-hal-3', word: 'ГХБ', category: 'hallucinogens', translation: 'GHB', language: 'ru' },
  { id: 'ru-hal-4', word: 'триазолам', category: 'psychotropic', translation: '三唑仑', language: 'ru' },

  // Actions
  { id: 'ru-act-1', word: 'трансграничная контрабанда наркотиков', category: 'actions', translation: '跨国毒品走私', language: 'ru' },
  { id: 'ru-act-2', word: 'изъятие наркотиков Монголия', category: 'actions', translation: '蒙古国毒品缉获', language: 'ru' },
  { id: 'ru-act-3', word: 'антинаркотическая операция ОДКБ', category: 'actions', translation: '集体安全条约组织禁毒行动', language: 'ru' },
  { id: 'ru-act-4', word: 'прекурсоры наркотиков', category: 'actions', translation: '毒品前体/易制毒化学品', language: 'ru' },
];

export const CATEGORY_LABELS = {
  traditional: '传统毒品 (Traditional)',
  cannabis: '大麻全系 (Cannabis)',
  amphetamine: '合成兴奋剂/苯丙胺 (Stimulants)',
  cnb: '安纳咖专项 (CNB/Anaga)',
  cathinone: '合成卡西酮/浴盐 (Cathinones)',
  fentanyl: '芬太尼全谱系 (Fentanyls)',
  hallucinogens: '致幻剂类 (Hallucinogens)',
  psychotropic: '精神管制药品 (Psychotropics)',
  precursors: '易制毒化学品 (Precursors)',
  actions: '执法案件行动 (Actions/Enforcement)'
};

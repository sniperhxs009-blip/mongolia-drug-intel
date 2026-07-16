import { TargetSite } from '../types';

export const TARGET_SITES: TargetSite[] = [
  // --- 一、蒙古国禁毒执法官方机构 ---
  {
    id: 'site-customs',
    name: '蒙古国海关总局 (Customs General Administration)',
    url: 'https://customs.gov.mn',
    queryDomain: 'customs.gov.mn',
    category: 'enforcement'
  },
  {
    id: 'site-bpo',
    name: '蒙古国边防总局 (General Authority for Border Protection)',
    url: 'https://bpo.gov.mn',
    queryDomain: 'bpo.gov.mn',
    category: 'enforcement'
  },
  {
    id: 'site-mojha',
    name: '蒙古国司法与内务部 (Ministry of Justice and Home Affairs)',
    url: 'https://mojha.gov.mn',
    queryDomain: 'mojha.gov.mn',
    category: 'enforcement'
  },
  {
    id: 'site-police',
    name: '蒙古国国家警察局缉毒分局 (National Police Agency - Anti-Narcotics)',
    url: 'https://police.gov.mn',
    queryDomain: 'police.gov.mn',
    category: 'enforcement'
  },
  {
    id: 'site-nema',
    name: '蒙古国紧急状况总局 (National Emergency Management Agency)',
    url: 'https://nema.gov.mn',
    queryDomain: 'nema.gov.mn',
    category: 'enforcement'
  },
  {
    id: 'site-nfa',
    name: '蒙古国国家法医总局 (National Forensic Agency)',
    url: 'https://nfa.gov.mn',
    queryDomain: 'nfa.gov.mn',
    category: 'enforcement'
  },

  // --- 二、蒙古国顶层政府、立法机构 ---
  {
    id: 'site-cabinet',
    name: '蒙古国政府内阁官网 (Government of Mongolia)',
    url: 'https://mongolia.gov.mn',
    queryDomain: 'mongolia.gov.mn',
    category: 'government'
  },
  {
    id: 'site-parliament',
    name: '蒙古国国家议会 (State Great Khural / Parliament)',
    url: 'https://parliament.mn',
    queryDomain: 'parliament.mn',
    category: 'government'
  },

  // --- 三、药物依赖康复中心 ---
  {
    id: 'site-ncmh',
    name: '蒙古国国家精神卫生中心 (National Center for Mental Health)',
    url: 'https://www.ncmh.gov.mn',
    queryDomain: 'ncmh.gov.mn',
    category: 'health'
  },
  {
    id: 'site-mohs',
    name: '蒙古国卫生部 (Ministry of Health)',
    url: 'https://www.mohs.mn',
    queryDomain: 'mohs.mn',
    category: 'health'
  },

  // --- 四、教育部门 ---
  {
    id: 'site-moe',
    name: '蒙古国教育科技部 (Ministry of Education and Science)',
    url: 'https://www.moe.gov.mn',
    queryDomain: 'moe.gov.mn',
    category: 'education'
  },

  // --- 五、蒙古国本土禁毒 NGO ---
  {
    id: 'site-ngo-betel',
    name: 'Betel Mongolia 蒙古国戒毒公益 NGO',
    url: 'https://betelmongolia.org',
    queryDomain: 'betelmongolia.org',
    category: 'ngo'
  },

  // --- 六、蒙古国权威官方媒体 ---
  {
    id: 'site-media-montsame',
    name: '蒙通社 MONTSAME (国家通讯社)',
    url: 'https://montsame.mn',
    queryDomain: 'montsame.mn',
    category: 'media'
  },
  {
    id: 'site-media-ikon',
    name: 'Ikon 新闻门户',
    url: 'https://ikon.mn',
    queryDomain: 'ikon.mn',
    category: 'media'
  },
  {
    id: 'site-media-shuum',
    name: 'Shuum 新闻',
    url: 'https://shuum.mn',
    queryDomain: 'shuum.mn',
    category: 'media'
  },
  {
    id: 'site-media-news',
    name: 'News.mn 新闻网',
    url: 'https://news.mn',
    queryDomain: 'news.mn',
    category: 'media'
  },

  // --- 七、CSTO 集体安全条约组织 ---
  {
    id: 'site-csto',
    name: 'CSTO/ОДКБ 集体安全条约组织官网',
    url: 'https://odkb-csto.org',
    queryDomain: 'odkb-csto.org',
    category: 'international'
  },

  // --- 八、国际权威禁毒官方组织 ---
  {
    id: 'site-unodc',
    name: 'UNODC 联合国毒品和犯罪问题办公室',
    url: 'https://unodc.org',
    queryDomain: 'unodc.org',
    category: 'international'
  },
  {
    id: 'site-interpol',
    name: 'INTERPOL 国际刑警组织',
    url: 'https://interpol.int',
    queryDomain: 'interpol.int',
    category: 'international'
  }
];

export const CATEGORY_NAMES = {
  enforcement: '禁毒与执法机构',
  government: '政府与立法机关',
  health: '医疗与康复机构',
  education: '教育与宣传部门',
  ngo: '本土禁毒 NGO',
  media: '权威官方媒体',
  international: '跨国/国际组织'
};

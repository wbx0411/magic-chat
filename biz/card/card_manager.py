from framework.algorithm.lcs_finder import longest_common_subsequence, longest_common_substring
from framework.algorithm.simple_bm25 import SimpleBM25
from framework.embedding.m3e_client import m3e_client
from transport.db.postgresdb import PostgresDB
from utils.config_utils import SysConfig
from utils.logger_utils import LoggerFactory

pgdb = PostgresDB('postgres_qin')
logger = LoggerFactory.get_logger(__name__)


def fetch_main_code(api_code):
    if '.' not in api_code:
        return api_code
    else:
        return api_code.split('.')[0]


def get_api_code(vector_result):
    api_code = ''
    api_desc = ''
    if vector_result is not None and len(vector_result) != 0:
        # main_code = fetch_main_code(vector_result[0][1])
        # api_code = configs['api_code_key'] + main_code + configs['api_code_key']
        api_code = fetch_main_code(vector_result[0][1])

        result = pgdb.query("SELECT * FROM miop_module_embedding WHERE api_code = %s", (api_code,))
        if result:
            api_desc = result[0]['api_desc']
            api_code = result[0]['api_code']
    return api_code, api_desc


def calculate_average_distance(ids_distances):
    # 初始化累加变量
    total_distance = 0

    # 遍历列表，累加距离
    for _, distance, _ in ids_distances:
        total_distance += distance

    # 计算平均值
    average_distance = total_distance / len(ids_distances)

    return average_distance


def find_best_matches(tuples_list, query_string):
    """
    在给定的字符串和键的元组列表中，找到并排序与查询字符串匹配的元组。
    最相关的结果优先排序。

    参数:
    tuples_list (list of tuples): 字符串和键的元组列表。
    query_string (str): 查询字符串。

    返回:
    list: 排序后的与查询字符串匹配的元组列表。
    """
    matches_info = []

    # 计算每个元组的最长公共子序列和最长公共子串长度
    for key, string in tuples_list:
        lcs = longest_common_subsequence(string, query_string)
        lcsstr = longest_common_substring(string, query_string)
        lcs_length = len(lcs)
        lcsstr_length = len(lcsstr)
        matches_info.append((string, key, lcs_length, lcsstr_length))

    # 根据最长公共子序列长度和最长公共子串长度排序
    # 首先按最长公共子序列长度降序排序，然后按最长公共子串长度降序排序
    sorted_matches = sorted(matches_info, key=lambda x: (-x[2], -x[3]))

    # 返回排序后的元组列表，不包括长度信息
    return [(key, string) for string, key, _, _ in sorted_matches]


class EmbeddingService:
    def __init__(self):
        self.configs = SysConfig.get_config()
        self.base_org_no = self.configs['test_org_no']
        self.embedding_client = m3e_client
        self.bm25 = SimpleBM25()
        self.top_k = self.configs['top_k']
        self.prompt_top_k = self.get('prompt_top_k', 1)

    def get_similar_vector_ids(self, search_text):
        logger.info("Getting similar vector ids for search text: %s", search_text)
        try:
            embedding_response = self.embedding_client.get_embeddings(
                [search_text], self.configs['m3e_model_name']
            )
            if embedding_response:
                embedding = embedding_response['data'][0]['embedding']

                # 查询欧式距离 (L2) 最近的向量
                sql = """
                    SELECT vector_id, api_desc, embedding <-> %s::vector AS distance 
                    FROM miop_module_embedding 
                    ORDER BY embedding <-> %s::vector LIMIT %s
                """
                results = pgdb.query(
                    sql,
                    (
                        embedding,
                        embedding,
                        self.top_k,
                    ),
                )

                vector_ids_distances = [
                    (result['vector_id'], result['distance'], result['api_desc'])
                    for result in results
                ]
                logger.info("Found similar vector ids: %s", vector_ids_distances)
                return vector_ids_distances
            else:
                return []  # 如果没有找到向量，则返回空列表
        except Exception as e:
            logger.error("An error occurred while getting similar vector ids: %s", e, exc_info=True)
            raise e

    @staticmethod
    def get_all_desc():
        results = pgdb.query("SELECT vector_id, api_desc FROM miop_module_embedding")
        return [(result['vector_id'], result['api_desc']) for result in results]

    def get_bm25_top_ids(self, search_text):
        top_k = self.bm25.query(self.get_all_desc(), search_text, self.top_k, 1)
        logger.info("Found similar bm25 ids: %s", top_k)
        return top_k

    @staticmethod
    def get_search_results_by_ids(ids_int, org_no):
        try:
            vector_ids = [result[0] for result in ids_int]
            sql = "SELECT * FROM miop_module_datas WHERE vector_id IN %s AND org_no = %s"
            search_results = pgdb.query(
                sql,
                (
                    tuple(vector_ids),
                    org_no,
                ),
            )
            results_dict = {
                result['vector_id']: (result['module_description'], result['api_code'])
                for result in search_results
            }
            sorted_search_results = [
                results_dict[vector_id] for vector_id in vector_ids if vector_id in results_dict
            ]

            return sorted_search_results
        except Exception as e:
            logger.error("An error occurred while fetching search results: %s", e, exc_info=True)
            raise e

    def vector_search(self, search_text, org_no):
        # 获取相似的向量ID和它们的距离
        ids_distances = self.get_similar_vector_ids(search_text)
        avg_distance = calculate_average_distance(ids_distances)
        logger.info(f"avg distance: {avg_distance}")
        if self.configs['card_distance_threshold'] < avg_distance:
            return []

        # 根据向量ID获取搜索结果
        ids_distance = [
            (int(vector_id), distance) for vector_id, distance, api_desc in ids_distances
        ]
        logger.info("Fetching search results by ids: %s", ids_distance)

        # 假设 ids_distances 已经定义
        ids_int = [(int(vector_id), api_desc) for vector_id, distance, api_desc in ids_distances]

        # bm25取top_k
        bm25 = self.get_bm25_top_ids(search_text)
        bm25_ids = [(int(vector_id), api_desc) for vector_id, api_desc in bm25]
        ids_int = list(set(ids_int).union(set(bm25_ids)))

        sorted_results = find_best_matches(ids_int, search_text)
        logger.info("sorted result: %s", sorted_results)
        search_results = self.get_search_results_by_ids(sorted_results, org_no)
        prompt_result = search_results[: self.prompt_top_k]

        # 打印搜索结果
        formatted_results = "\n".join(
            [f"module: {item[1]}, desc: {item[0]}" for item in prompt_result]
        )
        logger.debug("Performing vector search for text:\n%s", formatted_results)

        return prompt_result

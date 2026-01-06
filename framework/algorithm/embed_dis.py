import numpy as np


def l2_distance(point1, point2):
    """
    计算两个点之间的L2距离（欧几里得距离）

    :param point1: 第一个点的坐标，列表或数组
    :param point2: 第二个点的坐标，列表或数组
    :return: L2距离
    """
    point1 = np.array(point1)
    point2 = np.array(point2)
    return np.linalg.norm(point1 - point2)
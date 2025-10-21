# -*- coding: utf-8 -*-

import requests
from Aoeo.common.Logger import EnhancedLogger
from Aoeo.common.TokenGenerator import TokenGenerator


# 先创建实例，再调用方法
logger = EnhancedLogger()  # 实例化
POS = 'https://lawsonpos-dev.yorentown.com/pos/v1/pos'
urlPATH = "/getMemberDiscount"
URL = POS + urlPATH


def build_payload(access_token, user_code):
  """动态构建请求payload"""
  return {
    'accessToken': access_token,
    'userCode': user_code,
    'shopCode': '208888',
    'posNo': '84',
    'serialNumber': '6251909204',
    'paymentAmount': '6',
    'posVersion': '2',
    'extraInfo': '%7B%22memberAmount%22%3A0%7D',
    'commodityList': (
      '%5B%7B%22totalAmount%22%3A31.5%2C%22quantity%22%3A5%2C%22commodityBarcode%22%3A%22056227%22%2C%22price%22%3A89%2C'
      '%22discountInfoList%22%3A%5B%7B%22discountAmount%22%3A89%2C%22discountQuantity%22%3A1%7D%5D%2C%22totalDiscount%22%3A89%2C'
      '%22noOnlineDiscount%22%3A0%7D%2C%7B%22totalAmount%22%3A60%2C%22quantity%22%3A1%2C%22commodityBarcode%22%3A%22202216%22%2C'
      '%22price%22%3A60%2C%22discountInfoList%22%3A%5B%5D%2C%22totalDiscount%22%3A0%2C%22noOnlineDiscount%22%3A0%7D%5D'
    )
  }


# 使用示例
if __name__ == "__main__":

    Token = TokenGenerator(algorithm='md5')
    user_id_list = [1900413066794, 1900000000118, 1900000000132]

    for user_id in user_id_list:
      user_id_str = str(user_id)
      print(f"\n用户 {user_id} 的Token:")

      # 直接传递字符串key（不再用枚举）
      interfaces = {
        "优惠接口": "membershipVerification",
        "结算接口": "settlementTransactions",
        "退货接口": "returnInformation",
        "冲正接口": "couponCorrection"
      }

      for name, key in interfaces.items():
        token = Token.generate_token(key, user_id_str)
        # print(f"\n用户 {user_id} 的接口Tokens:")
        # logger.info(f"{user_id}{name}: {token}")
        print(f"   {name}: {token}")

access_token = Token.generate_token("membershipVerification", user_id)  # accessToken变量

print(access_token)
#
# payload = urlencode(build_payload(access_token, user_id_list))  # 使用变量构建payload
#
# headers = {'Content-Type': 'application/x-www-form-urlencoded'}
# response = requests.post(URL, headers=headers, data=payload)
#
# print(response.text)
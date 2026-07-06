def myformat(s):
    result=[]
    # current 当前行
    current=[]
    instring=False
    escape=False
    left=0
    right=0
    # print(len(s))
    for k in range(len(s)):
        # 字符串内部与结尾
        i=s[k]
        # print(i)
        if instring:
            current.append(i)
            if escape:
                escape=False
            elif i=='\\':
                escape=True
            elif i=='"':
                instring=False
            continue
        # 字符串起始
        if i=='"':
            instring=True
            current.append(i)
        elif i=='{':
            # 非字符串内的{,是一个对象的开始，重点判断要不要换行
            # 换行交给}判断
            left+=1
            current.append(i)
        elif i=='}':
            right+=1
            current.append(i)
            if left==right:
                # 换行
                current.append('\n')
                # 添加到result，current重置
                # result.append(current)
                # current=""
        else:
            current.append(i)
    return current
    
s="{\"a\\\"\": [{\"a\": 1}, {\"b\": 2}]}{\"a\": {\"b\": 1}}{}"
ss="{\"\\a\": \"\\a\"}{\"a\": {\"b\": 1}}{}"
a=myformat(s)
print("".join(a))


        
